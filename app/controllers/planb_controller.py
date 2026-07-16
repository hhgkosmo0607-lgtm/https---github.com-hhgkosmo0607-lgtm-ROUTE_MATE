from flask import Blueprint, request

from ..services import planb_service
from ..utils.decorators import require_planb_member
from ..utils.response import ApiError, error_response, success_response

planb_bp = Blueprint("planb", __name__)


@planb_bp.delete("/<int:planb_id>")
@require_planb_member("EDITOR")
def delete_planb(planb_id):
    try:
        planb_service.delete_planb(planb_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(None)


@planb_bp.post("/<int:planb_id>/activate")
@require_planb_member("EDITOR")
def activate_planb(planb_id):
    try:
        preview = planb_service.activate_planb(planb_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(preview)


@planb_bp.post("/<int:planb_id>/confirm")
@require_planb_member("EDITOR")
def confirm_planb(planb_id):
    body = request.get_json(silent=True) or {}
    try:
        schedule = planb_service.confirm_planb(planb_id, accept_overflow=bool(body.get("accept_overflow")))
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(
        {"schedule_id": schedule.schedule_id, "place": {"place_id": schedule.place.place_id, "name": schedule.place.name}}
    )


@planb_bp.post("/<int:planb_id>/reject")
@require_planb_member("EDITOR")
def reject_planb(planb_id):
    try:
        planb = planb_service.reject_planb(planb_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"planb_id": planb.planb_id, "status": planb.status})
