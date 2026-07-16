from flask import Blueprint, request

from ..services import planb_service, trip_service
from ..utils.decorators import require_schedule_member
from ..utils.response import ApiError, error_response, success_response
from .trip_controller import _schedule_payload

schedule_bp = Blueprint("schedules", __name__)


def _planb_payload(planb):
    return {
        "planb_id": planb.planb_id,
        "schedule_id": planb.schedule_id,
        "alt_place": {"place_id": planb.alt_place.place_id, "name": planb.alt_place.name},
        "trigger_type": planb.trigger_type,
        "priority": planb.priority,
        "rain_threshold": planb.rain_threshold,
        "status": planb.status,
    }


@schedule_bp.put("/<int:schedule_id>")
@require_schedule_member("EDITOR")
def update_schedule(schedule_id):
    body = request.get_json(silent=True) or {}
    try:
        schedule = trip_service.update_schedule(
            schedule_id,
            stay_min=body.get("stay_min"),
            memo=body.get("memo"),
            is_locked=body.get("is_locked"),
        )
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(_schedule_payload(schedule))


@schedule_bp.delete("/<int:schedule_id>")
@require_schedule_member("EDITOR")
def delete_schedule(schedule_id):
    try:
        trip_service.delete_schedule(schedule_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(None)


@schedule_bp.post("/<int:schedule_id>/planb")
@require_schedule_member("EDITOR")
def register_planb(schedule_id):
    body = request.get_json(silent=True) or {}
    try:
        planb = planb_service.register_planb(
            schedule_id,
            body.get("trigger_type"),
            priority=body.get("priority"),
            rain_threshold=body.get("rain_threshold"),
            alt_place_id=body.get("alt_place_id"),
            name=body.get("name"),
            category=body.get("category"),
            lat=body.get("lat"),
            lng=body.get("lng"),
            address=body.get("address"),
        )
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(_planb_payload(planb), 201)


@schedule_bp.get("/<int:schedule_id>/planb")
@require_schedule_member("VIEWER")
def list_planb(schedule_id):
    try:
        options = planb_service.list_planb(schedule_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"planb": [_planb_payload(p) for p in options]})


@schedule_bp.post("/<int:schedule_id>/revert")
@require_schedule_member("EDITOR")
def revert_schedule(schedule_id):
    try:
        schedule = planb_service.revert_schedule(schedule_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(_schedule_payload(schedule))
