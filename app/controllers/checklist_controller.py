from flask import Blueprint, request
from flask_login import current_user

from ..services import checklist_service
from ..utils.decorators import require_checklist_member
from ..utils.response import ApiError, error_response, success_response

checklist_bp = Blueprint("checklist", __name__)


def _payload(row):
    return {
        "check_id": row.check_id,
        "item": row.item,
        "is_done": row.is_done,
        "order_no": row.order_no,
        "checked_by": row.checked_by,
    }


@checklist_bp.put("/<int:check_id>")
@require_checklist_member("EDITOR")
def update_checklist_item(check_id):
    body = request.get_json(silent=True) or {}
    try:
        row = checklist_service.update_item(
            check_id, current_user, item=body.get("item"), is_done=body.get("is_done")
        )
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(_payload(row))


@checklist_bp.delete("/<int:check_id>")
@require_checklist_member("EDITOR")
def delete_checklist_item(check_id):
    try:
        checklist_service.delete_item(check_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response(None)
