from datetime import datetime

from flask_login import current_user
from sqlalchemy import func

from ..engines import route_engine
from ..extensions import db
from ..models.place import Place
from ..models.planb import PlanB
from ..models.schedule import Schedule
from ..utils.audit import log_event
from ..utils.response import ApiError
from . import trip_service

TRIGGER_TYPES = ("WAIT", "CLOSED", "RAIN", "MANUAL")


def _get_schedule_or_404(schedule_id):
    schedule = Schedule.query.filter_by(schedule_id=schedule_id).first()
    if schedule is None:
        raise ApiError("NOT_FOUND", "일정을 찾을 수 없습니다.", 404)
    return schedule


def register_planb(
    schedule_id, trigger_type, priority=None, rain_threshold=None,
    alt_place_id=None, name=None, category=None, lat=None, lng=None, address=None,
):
    """Plan B 등록 (FR-401/402)."""
    _get_schedule_or_404(schedule_id)

    if trigger_type not in TRIGGER_TYPES:
        raise ApiError("INVALID_INPUT", "trigger_type은 WAIT, CLOSED, RAIN, MANUAL 중 하나여야 합니다.", 400)

    if alt_place_id is not None:
        alt_place = Place.query.filter_by(place_id=alt_place_id).first()
        if alt_place is None:
            raise ApiError("INVALID_INPUT", "alt_place_id에 해당하는 장소를 찾을 수 없습니다.", 400)
    else:
        if not (name and category and lat is not None and lng is not None):
            raise ApiError("INVALID_INPUT", "alt_place_id 또는 name/category/lat/lng가 필요합니다.", 400)
        alt_place = Place(ext_source="USER", name=name, category=category, lat=lat, lng=lng, address=address)
        db.session.add(alt_place)
        db.session.flush()

    if priority is None:
        max_priority = (
            db.session.query(func.max(PlanB.priority)).filter(PlanB.schedule_id == schedule_id).scalar() or 0
        )
        priority = max_priority + 1
    elif PlanB.query.filter_by(schedule_id=schedule_id, priority=priority).first() is not None:
        raise ApiError("CONFLICT", f"우선순위 {priority}은(는) 이미 사용 중입니다.", 409)

    planb = PlanB(
        schedule_id=schedule_id,
        alt_place_id=alt_place.place_id,
        trigger_type=trigger_type,
        priority=priority,
        rain_threshold=rain_threshold if trigger_type == "RAIN" else None,
        status="READY",
    )
    db.session.add(planb)
    db.session.commit()
    return planb


def list_planb(schedule_id):
    _get_schedule_or_404(schedule_id)
    return PlanB.query.filter_by(schedule_id=schedule_id).order_by(PlanB.priority).all()


def delete_planb(planb_id):
    planb = PlanB.query.filter_by(planb_id=planb_id).first()
    if planb is None:
        raise ApiError("NOT_FOUND", "Plan B를 찾을 수 없습니다.", 404)
    db.session.delete(planb)
    db.session.commit()


def _get_planb_or_404(planb_id):
    planb = PlanB.query.filter_by(planb_id=planb_id).first()
    if planb is None:
        raise ApiError("NOT_FOUND", "Plan B를 찾을 수 없습니다.", 404)
    return planb


def _compute_reconstruction(planb):
    """해당 Day에서 대상 일정만 대체 장소로 바꿔 시뮬레이션한다 (DB는 건드리지 않는다)."""
    schedule = planb.schedule
    trip = trip_service.get_trip_or_404(schedule.trip_id)

    day_items = (
        Schedule.query.filter_by(trip_id=schedule.trip_id, day_no=schedule.day_no)
        .order_by(Schedule.order_no)
        .all()
    )
    transport = trip_service.owner_transport(trip)

    def to_input(s):
        place = planb.alt_place if s.schedule_id == schedule.schedule_id else s.place
        return route_engine.DayItemInput(
            place_id=place.place_id,
            lat=float(place.lat),
            lng=float(place.lng),
            stay_min=s.stay_min,
            is_locked=s.is_locked,
            start_min=(s.start_time.hour * 60 + s.start_time.minute) if (s.is_locked and s.start_time) else None,
        )

    inputs = [to_input(s) for s in day_items]
    results = route_engine.recalc_day(inputs, transport, trip.day_start)

    day_end_min = trip.day_end.hour * 60 + trip.day_end.minute
    overflow = [r for r in results if r.start_min + r.stay_min > day_end_min]

    old_total = sum((s.move_min or 0) for s in day_items)
    new_total = sum((r.move_min or 0) for r in results)

    return schedule, day_items, results, overflow, new_total - old_total


def activate_planb(planb_id):
    """Plan B 발동 → 재구성안 미리보기 (FR-405, 비파괴적)."""
    planb = _get_planb_or_404(planb_id)
    if planb.status != "READY":
        raise ApiError("CONFLICT", "이미 처리된 Plan B입니다.", 409)

    schedule, day_items, results, overflow, move_min_delta = _compute_reconstruction(planb)

    return {
        "planb_id": planb.planb_id,
        "trigger": planb.trigger_type,
        "replaced": {"from": schedule.place.name, "to": planb.alt_place.name},
        "recalc_summary": {
            "affected_schedules": len(day_items),
            "move_min_delta": move_min_delta,
            "warnings": ["일부 일정이 활동 시간을 초과합니다."] if overflow else [],
        },
        "preview_day": [
            {
                "place_id": r.place_id,
                "order_no": r.order_no,
                "start_time": _fmt_minutes(r.start_min),
                "stay_min": r.stay_min,
                "move_min": r.move_min,
                "move_km": r.move_km,
            }
            for r in results
        ],
        "confirm_url": f"/api/planb/{planb.planb_id}/confirm",
    }


def _fmt_minutes(minutes):
    minutes %= 24 * 60
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def confirm_planb(planb_id, accept_overflow=False):
    """재구성안 승인·확정 (FR-406). 활동시간 초과분은 명시적 승인 없이는 적용하지 않는다(TC-305)."""
    planb = _get_planb_or_404(planb_id)
    if planb.status != "READY":
        raise ApiError("CONFLICT", "이미 처리된 Plan B입니다.", 409)

    schedule, day_items, results, overflow, _ = _compute_reconstruction(planb)
    if overflow and not accept_overflow:
        raise ApiError(
            "CONSTRAINT_VIOLATION",
            f"재구성 시 {len(overflow)}건의 일정이 활동 시간을 초과합니다. accept_overflow=true로 재요청하세요.",
            422,
        )

    schedule.original_place_id = schedule.place_id
    schedule.place_id = planb.alt_place_id

    for s in day_items:
        s.order_no = -(s.schedule_id)
    db.session.flush()
    for s, r in zip(day_items, results):
        s.order_no = r.order_no
        s.start_time = trip_service.minutes_to_time(r.start_min)
        s.move_min = r.move_min
        s.move_km = r.move_km

    planb.status = "ACTIVATED"
    planb.activated_at = datetime.utcnow()
    db.session.commit()
    log_event(
        "PLANB_ACTIVATED",
        user_id=current_user.get_id(),
        planb_id=planb.planb_id,
        schedule_id=schedule.schedule_id,
        trigger_type=planb.trigger_type,
    )
    return schedule


def reject_planb(planb_id):
    planb = _get_planb_or_404(planb_id)
    if planb.status != "READY":
        raise ApiError("CONFLICT", "이미 처리된 Plan B입니다.", 409)
    planb.status = "REJECTED"
    db.session.commit()
    return planb


def revert_schedule(schedule_id):
    """되돌리기 — Plan B로 교체된 일정을 원래 장소로 복원한다 (9.3.3절)."""
    schedule = _get_schedule_or_404(schedule_id)
    if schedule.original_place_id is None:
        raise ApiError("CONSTRAINT_VIOLATION", "되돌릴 대체 이력이 없습니다.", 422)

    schedule.place_id = schedule.original_place_id
    schedule.original_place_id = None
    db.session.commit()
    return schedule
