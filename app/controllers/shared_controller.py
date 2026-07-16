from flask import Blueprint

from ..services import trip_service
from ..utils.response import ApiError, error_response, success_response
from .trip_controller import _schedule_payload, _trip_payload

shared_bp = Blueprint("shared", __name__)


@shared_bp.get("/<string:token>")
def get_shared_trip(token):
    """공유 토큰을 통한 읽기 전용 조회 (FR-604). 로그인 불필요."""
    try:
        trip = trip_service.get_trip_by_share_token(token)
        schedules = trip_service.list_schedules(trip.trip_id)
    except ApiError as e:
        return error_response(e.code, e.message, e.status)

    payload = _trip_payload(trip)
    payload["schedules"] = [_schedule_payload(s) for s in schedules]
    return success_response(payload)
