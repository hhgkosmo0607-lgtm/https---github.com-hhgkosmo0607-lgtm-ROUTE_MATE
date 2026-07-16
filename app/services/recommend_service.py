from sqlalchemy import func

from ..engines import recommender
from ..extensions import db
from ..models.place import Place
from ..models.recommendation import Recommendation
from ..models.schedule import UNASSIGNED_DAY, Schedule
from ..utils.response import ApiError
from . import trip_service

REC_TYPE_CATEGORIES = {
    "ATTRACTION": ["ATTRACTION"],
    "FOOD": ["RESTAURANT"],
    "CAFE": ["CAFE"],
    "GAP_FILL": ["ATTRACTION", "RESTAURANT", "CAFE"],
    "PLANB_ALT": ["ATTRACTION", "RESTAURANT", "CAFE"],  # 대안 소진 시 즉시 AI 추천 (FR-407)
}
CANDIDATE_RADIUS_KM = 5


def _effective_profile(user):
    profile = user.profile
    if profile is None:
        return recommender.ProfileInput(allergy=[], budget_level=None, interests={})
    return recommender.ProfileInput(
        allergy=profile.allergy or [],
        budget_level=profile.budget_level,
        interests=profile.interests or {},
    )


def _resolve_anchor(trip_id, near_schedule_id, lat, lng):
    if lat is not None and lng is not None:
        return float(lat), float(lng)

    if near_schedule_id is not None:
        schedule = Schedule.query.filter_by(trip_id=trip_id, schedule_id=near_schedule_id).first()
        if schedule is None:
            raise ApiError("INVALID_INPUT", "near_schedule_id에 해당하는 일정을 찾을 수 없습니다.", 400)
        return float(schedule.place.lat), float(schedule.place.lng)

    first = Schedule.query.filter_by(trip_id=trip_id).order_by(Schedule.day_no, Schedule.order_no).first()
    if first is not None:
        return float(first.place.lat), float(first.place.lng)

    raise ApiError(
        "INVALID_INPUT", "추천 기준 위치가 없습니다. 먼저 장소를 추가하거나 near_schedule_id/lat/lng를 지정하세요.", 400
    )


def _gather_candidates(anchor, categories, excluded_place_ids):
    lat, lng = anchor
    lat_margin = CANDIDATE_RADIUS_KM / 111.0  # 위도 1도 ≈ 111km
    lng_margin = CANDIDATE_RADIUS_KM / 88.0  # 경도 1도 ≈ 88km (한국 위도 기준 근사)

    rows = (
        Place.query.filter(
            Place.category.in_(categories),
            Place.lat.between(lat - lat_margin, lat + lat_margin),
            Place.lng.between(lng - lng_margin, lng + lng_margin),
        )
        .filter(~Place.place_id.in_(excluded_place_ids) if excluded_place_ids else True)
        .all()
    )
    return [
        recommender.CandidateInput(
            place_id=p.place_id, name=p.name, category=p.category, lat=float(p.lat), lng=float(p.lng),
            price_level=p.price_level,
        )
        for p in rows
    ]


def create_recommendations(trip_id, user, rec_type, near_schedule_id=None, lat=None, lng=None, count=5):
    """추천 생성 파이프라인 (FR-301~304, 9.2.1절). Claude API 미연동 상태이므로
    8.3절 규칙 기반 폴백을 기본 스코어링으로 사용한다."""
    trip = trip_service.get_trip_or_404(trip_id)
    if rec_type not in REC_TYPE_CATEGORIES:
        raise ApiError("INVALID_INPUT", "type은 ATTRACTION, FOOD, CAFE, GAP_FILL 중 하나여야 합니다.", 400)

    anchor = _resolve_anchor(trip_id, near_schedule_id, lat, lng)
    existing_place_ids = {s.place_id for s in Schedule.query.filter_by(trip_id=trip_id).all()}
    candidates = _gather_candidates(anchor, REC_TYPE_CATEGORIES[rec_type], existing_place_ids)

    profile = _effective_profile(trip.owner)
    transport = trip_service.owner_transport(trip)
    scored = recommender.recommend(candidates, profile, existing_place_ids, anchor, transport, count)

    records = []
    for s in scored:
        record = Recommendation(
            trip_id=trip_id, place_id=s.place_id, rec_type=rec_type, reason=s.reason, score=round(s.score / 100, 3)
        )
        db.session.add(record)
        records.append(record)
    db.session.commit()
    return records


def list_recommendations(trip_id):
    trip_service.get_trip_or_404(trip_id)
    return Recommendation.query.filter_by(trip_id=trip_id).order_by(Recommendation.created_at.desc()).all()


def _get_recommendation_or_404(rec_id):
    record = Recommendation.query.filter_by(rec_id=rec_id).first()
    if record is None:
        raise ApiError("NOT_FOUND", "추천 이력을 찾을 수 없습니다.", 404)
    return record


def accept_recommendation(rec_id):
    """추천 수락 → 미배치 보관함에 일정으로 반영 (FR-306)."""
    record = _get_recommendation_or_404(rec_id)
    if record.is_accepted is not None:
        raise ApiError("CONFLICT", "이미 처리된 추천입니다.", 409)

    record.is_accepted = True

    max_order = (
        db.session.query(func.max(Schedule.order_no))
        .filter(Schedule.trip_id == record.trip_id, Schedule.day_no == UNASSIGNED_DAY)
        .scalar()
        or 0
    )
    schedule = Schedule(
        trip_id=record.trip_id, place_id=record.place_id, day_no=UNASSIGNED_DAY, order_no=max_order + 1
    )
    db.session.add(schedule)
    db.session.commit()
    return record, schedule


def reject_recommendation(rec_id):
    record = _get_recommendation_or_404(rec_id)
    if record.is_accepted is not None:
        raise ApiError("CONFLICT", "이미 처리된 추천입니다.", 409)
    record.is_accepted = False
    db.session.commit()
    return record
