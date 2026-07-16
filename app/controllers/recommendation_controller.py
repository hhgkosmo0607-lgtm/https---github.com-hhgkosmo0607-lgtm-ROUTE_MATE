from flask import Blueprint

from ..services import recommend_service
from ..utils.decorators import require_recommendation_member
from ..utils.response import ApiError, error_response, success_response

recommendation_bp = Blueprint("recommendations", __name__)


def _payload(rec):
    return {
        "rec_id": rec.rec_id,
        "rec_type": rec.rec_type,
        "place_id": rec.place_id,
        "score": float(rec.score),
        "reason": rec.reason,
        "is_accepted": rec.is_accepted,
    }


@recommendation_bp.post("/<int:rec_id>/accept")
@require_recommendation_member("EDITOR")
def accept(rec_id):
    try:
        record, schedule = recommend_service.accept_recommendation(rec_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"recommendation": _payload(record), "schedule_id": schedule.schedule_id})


@recommendation_bp.post("/<int:rec_id>/reject")
@require_recommendation_member("EDITOR")
def reject(rec_id):
    try:
        record = recommend_service.reject_recommendation(rec_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"recommendation": _payload(record)})
