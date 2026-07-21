from flask import current_app
from sqlalchemy import func

from ..adapters.gemini_adapter import GeminiAdapter
from ..adapters.osm_adapter import OSMAdapter
from ..engines import recommender
from ..extensions import db
from ..models.place import Place
from ..models.recommendation import Recommendation
from ..models.schedule import UNASSIGNED_DAY, Schedule
from ..utils.response import ApiError
from . import trip_service
from .place_service import _guess_category

REC_TYPE_CATEGORIES = {
    "ATTRACTION": ["ATTRACTION"],
    "FOOD": ["RESTAURANT"],
    "CAFE": ["CAFE"],
    "GAP_FILL": ["ATTRACTION", "RESTAURANT", "CAFE"],
    "PLANB_ALT": ["ATTRACTION", "RESTAURANT", "CAFE"],  # 대안 소진 시 즉시 AI 추천 (FR-407)
}
# 후보 자동 수집(Overpass) 시 rec_type별 태그 필터 (9.2.1절 ① 후보 수집)
REC_TAG_FILTERS = {
    "FOOD": ("amenity", "restaurant|fast_food|food_court"),
    "CAFE": ("amenity", "cafe"),
    "ATTRACTION": ("tourism", "attraction|museum|gallery|viewpoint|zoo|theme_park"),
}
CANDIDATE_RADIUS_KM = 5
MIN_CANDIDATES = 10  # 이보다 적으면 주변 실장소를 자동 수집한다
COLLECT_DLAT, COLLECT_DLNG = 0.018, 0.0225  # 수집 반경 약 2km


def _map_adapter():
    if not current_app.config.get("MAP_ADAPTER_ENABLED"):
        return None
    return OSMAdapter(contact_email=current_app.config.get("MAP_CONTACT_EMAIL"))


def _ai_adapter():
    api_key = current_app.config.get("GEMINI_API_KEY")
    if not api_key:
        return None
    return GeminiAdapter(api_key, model=current_app.config.get("GEMINI_MODEL", "gemini-2.0-flash"))


def _score(filtered, profile, anchor, transport, count):
    """스코어링 (9.2.1절 ③): Gemini 우선 시도, 실패/미설정 시 규칙 기반 폴백(8.3절)."""
    adapter = _ai_adapter()
    if adapter is not None:
        try:
            raw = adapter.score_candidates(filtered, profile, anchor, transport, count)
            by_id = {c.place_id: c for c in filtered}
            scored = [
                recommender.ScoredCandidate(
                    place_id=item["place_id"],
                    score=round(min(100.0, max(0.0, float(item["score"]))), 1),
                    reason=str(item["reason"])[:300],
                )
                for item in raw
                if isinstance(item, dict) and item.get("place_id") in by_id
            ]
            if scored:
                scored.sort(key=lambda s: s.score, reverse=True)
                return scored[:count]
            current_app.logger.warning("Gemini returned no candidates matching the pool, falling back")
        except Exception:
            current_app.logger.warning("Gemini scoring failed, falling back to rule-based", exc_info=True)

    return recommender.score_candidates(filtered, profile, anchor, transport, count)


def _effective_profile(user):
    profile = user.profile
    if profile is None:
        return recommender.ProfileInput(allergy=[], budget_level=None, interests={})
    return recommender.ProfileInput(
        allergy=profile.allergy or [],
        budget_level=profile.budget_level,
        interests=profile.interests or {},
    )


def _resolve_anchor(trip, near_schedule_id, lat, lng):
    if lat is not None and lng is not None:
        return float(lat), float(lng)

    if near_schedule_id is not None:
        schedule = Schedule.query.filter_by(trip_id=trip.trip_id, schedule_id=near_schedule_id).first()
        if schedule is None:
            raise ApiError("INVALID_INPUT", "near_schedule_id에 해당하는 일정을 찾을 수 없습니다.", 400)
        return float(schedule.place.lat), float(schedule.place.lng)

    first = (
        Schedule.query.filter_by(trip_id=trip.trip_id).order_by(Schedule.day_no, Schedule.order_no).first()
    )
    if first is not None:
        return float(first.place.lat), float(first.place.lng)

    # 일정이 하나도 없으면 여행 지역명을 지오코딩해 기준점으로 사용 (FR-301: 지역 기반 추천)
    adapter = _map_adapter()
    if adapter is not None:
        try:
            results = adapter.geocode(trip.region, limit=1)
            if results:
                return results[0].lat, results[0].lng
        except Exception:
            current_app.logger.warning("region geocode failed for anchor", exc_info=True)

    raise ApiError(
        "INVALID_INPUT", "추천 기준 위치가 없습니다. 먼저 장소를 추가하거나 near_schedule_id/lat/lng를 지정하세요.", 400
    )


def _ensure_candidates(anchor, rec_type, excluded_place_ids):
    """후보가 부족하면 Overpass에서 주변 실장소를 수집해 PLACE에 채운다 (9.2.1절 ①).

    수집 장소는 (ext_source="OSM", ext_id) 복합 UNIQUE로 중복 저장이 방지된다.
    """
    adapter = _map_adapter()
    if adapter is None:
        return
    if len(_gather_candidates(anchor, REC_TYPE_CATEGORIES[rec_type], excluded_place_ids)) >= MIN_CANDIDATES:
        return

    lat, lng = anchor
    try:
        pois = adapter.nearby_pois(
            lat - COLLECT_DLAT, lng - COLLECT_DLNG, lat + COLLECT_DLAT, lng + COLLECT_DLNG,
            tag_filter=REC_TAG_FILTERS.get(rec_type),
        )
    except Exception:
        current_app.logger.warning("candidate auto-collect failed", exc_info=True)
        return

    ext_ids = [p.ext_id for p in pois if p.ext_id]
    existing = {
        e for (e,) in db.session.query(Place.ext_id)
        .filter(Place.ext_source == "OSM", Place.ext_id.in_(ext_ids))
        .all()
    }
    added = 0
    for dto in pois:
        if not dto.ext_id or dto.ext_id in existing:
            continue
        db.session.add(
            Place(
                ext_source="OSM",
                ext_id=dto.ext_id,
                name=dto.name[:100],
                category=_guess_category(dto.osm_category, dto.osm_type),
                lat=dto.lat,
                lng=dto.lng,
            )
        )
        added += 1
    if added:
        db.session.commit()


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
    """추천 생성 파이프라인 (FR-301~304, 9.2.1절). ③ 스코어링 단계는 GEMINI_API_KEY
    설정 시 Gemini를 우선 시도하고, 미설정이거나 실패하면 8.3절 규칙 기반 폴백을 쓴다."""
    trip = trip_service.get_trip_or_404(trip_id)
    if rec_type not in REC_TYPE_CATEGORIES:
        raise ApiError("INVALID_INPUT", "type은 ATTRACTION, FOOD, CAFE, GAP_FILL 중 하나여야 합니다.", 400)

    anchor = _resolve_anchor(trip, near_schedule_id, lat, lng)
    existing_place_ids = {s.place_id for s in Schedule.query.filter_by(trip_id=trip_id).all()}
    _ensure_candidates(anchor, rec_type, existing_place_ids)
    candidates = _gather_candidates(anchor, REC_TYPE_CATEGORIES[rec_type], existing_place_ids)

    profile = _effective_profile(trip.owner)
    transport = trip_service.owner_transport(trip)
    filtered = recommender.hard_filter(candidates, profile, existing_place_ids)
    scored = _score(filtered, profile, anchor, transport, count)

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
