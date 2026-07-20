from datetime import datetime, time

from flask import Blueprint, request
from flask_login import current_user, login_required

from ..extensions import limiter
from ..services import checklist_service, expense_service, recommend_service, trip_service
from ..utils.decorators import require_trip_member
from ..utils.response import ApiError, error_response, success_response

trip_bp = Blueprint("trips", __name__)

REC_TYPES = ("ATTRACTION", "FOOD", "CAFE", "GAP_FILL", "PLANB_ALT")


def _recommendation_payload(rec):
    return {
        "rec_id": rec.rec_id,
        "rec_type": rec.rec_type,
        "place": {"place_id": rec.place.place_id, "name": rec.place.name, "category": rec.place.category},
        "score": float(rec.score),
        "reason": rec.reason,
        "is_accepted": rec.is_accepted,
    }


def _checklist_payload(row):
    return {
        "check_id": row.check_id,
        "item": row.item,
        "is_done": row.is_done,
        "order_no": row.order_no,
        "checked_by": row.checked_by,
    }


def _expense_payload(row):
    return {
        "expense_id": row.expense_id,
        "category": row.category,
        "item_type": row.item_type,
        "amount": row.amount,
        "memo": row.memo,
        "spent_at": row.spent_at.isoformat() if row.spent_at else None,
        "created_by": row.created_by,
    }


def _member_payload(member):
    return {
        "member_id": member.member_id,
        "user_id": member.user_id,
        "nickname": member.user.nickname,
        "role": member.role,
    }


def _trip_payload(trip):
    return {
        "trip_id": trip.trip_id,
        "title": trip.title,
        "start_date": trip.start_date.isoformat(),
        "end_date": trip.end_date.isoformat(),
        "region": trip.region,
        "day_start": trip.day_start.strftime("%H:%M"),
        "day_end": trip.day_end.strftime("%H:%M"),
        "status": trip.status,
    }


def _schedule_payload(schedule):
    return {
        "schedule_id": schedule.schedule_id,
        "day_no": schedule.day_no,
        "order_no": schedule.order_no,
        "place": {
            "place_id": schedule.place.place_id,
            "name": schedule.place.name,
            "category": schedule.place.category,
            "lat": float(schedule.place.lat),
            "lng": float(schedule.place.lng),
        },
        "start_time": schedule.start_time.strftime("%H:%M") if schedule.start_time else None,
        "stay_min": schedule.stay_min,
        "move_min": schedule.move_min,
        "move_km": float(schedule.move_km) if schedule.move_km is not None else None,
        "is_locked": schedule.is_locked,
        "original_place_id": schedule.original_place_id,
        "memo": schedule.memo,
    }


def _parse_date(value):
    return datetime.fromisoformat(value).date()


def _parse_time(value):
    if not value:
        return None
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


@trip_bp.get("")
@login_required
def list_trips():
    trips = trip_service.list_trips_for_user(current_user)
    return success_response({"trips": [_trip_payload(t) for t in trips]})


@trip_bp.post("")
@login_required
def create_trip():
    body = request.get_json(silent=True) or {}
    try:
        start_date = _parse_date(body["start_date"])
        end_date = _parse_date(body["end_date"])
    except (KeyError, ValueError):
        return error_response("INVALID_INPUT", "시작일/종료일 형식이 올바르지 않습니다.", 400)

    try:
        trip = trip_service.create_trip(
            current_user,
            (body.get("title") or "").strip(),
            start_date,
            end_date,
            (body.get("region") or "").strip(),
            _parse_time(body.get("day_start")),
            _parse_time(body.get("day_end")),
        )
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(_trip_payload(trip), 201)


@trip_bp.get("/<int:trip_id>")
@require_trip_member("VIEWER")
def get_trip(trip_id):
    try:
        trip = trip_service.get_trip_or_404(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(_trip_payload(trip))


@trip_bp.put("/<int:trip_id>")
@require_trip_member("EDITOR")
def update_trip(trip_id):
    body = request.get_json(silent=True) or {}
    fields = {}
    try:
        if "title" in body:
            fields["title"] = body["title"]
        if "region" in body:
            fields["region"] = body["region"]
        if "start_date" in body:
            fields["start_date"] = _parse_date(body["start_date"])
        if "end_date" in body:
            fields["end_date"] = _parse_date(body["end_date"])
        if "day_start" in body:
            fields["day_start"] = _parse_time(body["day_start"])
        if "day_end" in body:
            fields["day_end"] = _parse_time(body["day_end"])
    except ValueError:
        return error_response("INVALID_INPUT", "요청 값의 형식이 올바르지 않습니다.", 400)

    try:
        trip = trip_service.update_trip(trip_id, **fields)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(_trip_payload(trip))


@trip_bp.delete("/<int:trip_id>")
@require_trip_member("OWNER")
def delete_trip(trip_id):
    try:
        trip_service.delete_trip(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(None)


@trip_bp.post("/<int:trip_id>/places")
@require_trip_member("EDITOR")
def add_place(trip_id):
    body = request.get_json(silent=True) or {}
    if not all(k in body for k in ("name", "category", "lat", "lng")):
        return error_response("INVALID_INPUT", "name, category, lat, lng는 필수입니다.", 400)

    try:
        place, schedule = trip_service.add_place(
            trip_id, body["name"], body["category"], body["lat"], body["lng"], body.get("address")
        )
    except ApiError as e:
        return error_response(e.code, e.message, e.status)

    return success_response(
        {
            "place_id": place.place_id,
            "name": place.name,
            "category": place.category,
            "lat": float(place.lat),
            "lng": float(place.lng),
            "schedule_id": schedule.schedule_id,
        },
        201,
    )


@trip_bp.delete("/<int:trip_id>/places/<int:place_id>")
@require_trip_member("EDITOR")
def remove_place(trip_id, place_id):
    try:
        trip_service.remove_place(trip_id, place_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(None)


@trip_bp.get("/<int:trip_id>/schedules")
@require_trip_member("VIEWER")
def list_schedules(trip_id):
    try:
        schedules = trip_service.list_schedules(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"schedules": [_schedule_payload(s) for s in schedules]})


@trip_bp.put("/<int:trip_id>/schedules/order")
@require_trip_member("EDITOR")
def reorder_schedule(trip_id):
    body = request.get_json(silent=True) or {}
    if not all(k in body for k in ("schedule_id", "day_no", "order_no")):
        return error_response("INVALID_INPUT", "schedule_id, day_no, order_no는 필수입니다.", 400)

    try:
        affected_days = trip_service.reorder_schedule(
            trip_id, body["schedule_id"], int(body["day_no"]), int(body["order_no"])
        )
        schedules = trip_service.list_schedules(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)

    changed = [_schedule_payload(s) for s in schedules if s.day_no in affected_days]
    return success_response({"affected_days": affected_days, "schedules": changed})


@trip_bp.post("/<int:trip_id>/route")
@require_trip_member("EDITOR")
def generate_route(trip_id):
    body = request.get_json(silent=True) or {}
    transport = body.get("transport")
    if transport is not None and transport not in ("WALK", "TRANSIT", "CAR"):
        return error_response("INVALID_INPUT", "transport는 WALK, TRANSIT, CAR 중 하나여야 합니다.", 400)

    try:
        day_start = _parse_time(body.get("day_start"))
        day_end = _parse_time(body.get("day_end"))
    except ValueError:
        return error_response("INVALID_INPUT", "day_start/day_end 형식이 올바르지 않습니다.", 400)

    try:
        total_days, result = trip_service.generate_route(trip_id, transport, day_start, day_end)
        schedules = trip_service.list_schedules(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)

    by_day = {}
    for s in schedules:
        if s.day_no == 0:
            continue
        by_day.setdefault(s.day_no, []).append(_schedule_payload(s))

    return success_response(
        {
            "total_days": total_days,
            "total_move_min": result.total_move_min,
            "total_move_km": result.total_move_km,
            "days": [{"day_no": day_no, "schedules": items} for day_no, items in sorted(by_day.items())],
            "unassigned_count": len(result.unassigned),
            "approximate": result.used_fallback,  # 8.3절: 근사치 배지 표시 여부
        }
    )


@trip_bp.get("/<int:trip_id>/gaps")
@require_trip_member("VIEWER")
def get_gaps(trip_id):
    """빈 일정 자동 감지 (FR-303) — 60분 이상 공백 목록."""
    try:
        gaps = trip_service.detect_gaps(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"gaps": gaps})


@trip_bp.post("/<int:trip_id>/recommendations")
@limiter.limit("3 per minute", key_func=lambda: str(current_user.get_id()))  # 8.4절: 사용자당 분당 3회
@require_trip_member("EDITOR")
def create_recommendations(trip_id):
    body = request.get_json(silent=True) or {}
    rec_type = body.get("type")
    if rec_type not in REC_TYPES:
        return error_response("INVALID_INPUT", "type은 ATTRACTION, FOOD, CAFE, GAP_FILL 중 하나여야 합니다.", 400)

    try:
        records = recommend_service.create_recommendations(
            trip_id,
            current_user,
            rec_type,
            near_schedule_id=body.get("near_schedule_id"),
            lat=body.get("lat"),
            lng=body.get("lng"),
            count=body.get("count", 5),
        )
    except ApiError as e:
        return error_response(e.code, e.message, e.status)

    return success_response({"recommendations": [_recommendation_payload(r) for r in records]}, 201)


@trip_bp.get("/<int:trip_id>/recommendations")
@require_trip_member("VIEWER")
def list_recommendations(trip_id):
    try:
        records = recommend_service.list_recommendations(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"recommendations": [_recommendation_payload(r) for r in records]})


@trip_bp.get("/<int:trip_id>/checklist")
@require_trip_member("VIEWER")
def get_checklist(trip_id):
    try:
        items = checklist_service.list_items(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"checklist": [_checklist_payload(i) for i in items]})


@trip_bp.post("/<int:trip_id>/checklist")
@require_trip_member("EDITOR")
def add_checklist_item(trip_id):
    body = request.get_json(silent=True) or {}
    try:
        row = checklist_service.add_item(trip_id, (body.get("item") or "").strip())
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(_checklist_payload(row), 201)


@trip_bp.get("/<int:trip_id>/expenses")
@require_trip_member("VIEWER")
def get_expenses(trip_id):
    try:
        rows = expense_service.list_expenses(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"expenses": [_expense_payload(r) for r in rows]})


@trip_bp.post("/<int:trip_id>/expenses")
@require_trip_member("EDITOR")
def add_expense(trip_id):
    body = request.get_json(silent=True) or {}
    try:
        row = expense_service.add_expense(
            trip_id,
            current_user,
            body.get("category"),
            body.get("item_type"),
            body.get("amount"),
            memo=body.get("memo"),
            spent_at=body.get("spent_at"),
        )
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(_expense_payload(row), 201)


@trip_bp.get("/<int:trip_id>/expenses/summary")
@require_trip_member("VIEWER")
def get_expenses_summary(trip_id):
    try:
        data = expense_service.summary(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(data)


@trip_bp.post("/<int:trip_id>/share/link")
@require_trip_member("OWNER")
def create_share_link(trip_id):
    try:
        token = trip_service.generate_share_link(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"share_token": token})


@trip_bp.delete("/<int:trip_id>/share/link")
@require_trip_member("OWNER")
def delete_share_link(trip_id):
    try:
        trip_service.revoke_share_link(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(None)


@trip_bp.get("/<int:trip_id>/members")
@require_trip_member("VIEWER")
def get_members(trip_id):
    try:
        members = trip_service.list_members(trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"members": [_member_payload(m) for m in members]})


@trip_bp.post("/<int:trip_id>/members")
@require_trip_member("OWNER")
def invite_member(trip_id):
    body = request.get_json(silent=True) or {}
    try:
        member = trip_service.invite_member(trip_id, body.get("email"), body.get("role", "VIEWER"))
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(_member_payload(member), 201)


@trip_bp.put("/<int:trip_id>/members/<int:user_id>")
@require_trip_member("OWNER")
def update_member(trip_id, user_id):
    body = request.get_json(silent=True) or {}
    try:
        member = trip_service.update_member_role(trip_id, user_id, body.get("role"))
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(_member_payload(member))


@trip_bp.post("/<int:trip_id>/clone")
@require_trip_member("VIEWER")
def clone_trip(trip_id):
    try:
        new_trip = trip_service.clone_trip(trip_id, current_user)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(_trip_payload(new_trip), 201)
