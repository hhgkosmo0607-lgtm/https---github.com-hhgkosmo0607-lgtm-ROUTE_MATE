from functools import wraps

from flask import request
from flask_login import current_user

from .audit import log_event
from .response import error_response

ROLE_RANK = {"VIEWER": 1, "EDITOR": 2, "OWNER": 3}


def _forbidden():
    """403 응답 + 감사 로그 (11.1/11.4절 권한 거부 기록)."""
    log_event("ACCESS_DENIED", user_id=current_user.get_id(), path=request.path)
    return error_response("FORBIDDEN", "권한이 없습니다.", 403)


def require_trip_member(min_role="VIEWER"):
    """Require the current user to be a member of the trip with at least min_role.

    Non-members get 404 (not 403) so resource existence isn't leaked to
    outsiders, per 설계서 11.1.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from ..models.trip_member import TripMember

            if not current_user.is_authenticated:
                return error_response("UNAUTHORIZED", "인증이 필요합니다.", 401)

            trip_id = kwargs.get("trip_id")
            member = TripMember.query.filter_by(trip_id=trip_id, user_id=current_user.user_id).first()
            if member is None:
                return error_response("NOT_FOUND", "요청한 자원을 찾을 수 없습니다.", 404)
            if ROLE_RANK[member.role] < ROLE_RANK[min_role]:
                return _forbidden()

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_recommendation_member(min_role="VIEWER"):
    """Like require_trip_member, but the route is keyed by rec_id instead of
    trip_id (/api/recommendations/{recId}, 7.3.4절)."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from ..models.recommendation import Recommendation
            from ..models.trip_member import TripMember

            if not current_user.is_authenticated:
                return error_response("UNAUTHORIZED", "인증이 필요합니다.", 401)

            rec_id = kwargs.get("rec_id")
            record = Recommendation.query.filter_by(rec_id=rec_id).first()
            if record is None:
                return error_response("NOT_FOUND", "요청한 자원을 찾을 수 없습니다.", 404)

            member = TripMember.query.filter_by(trip_id=record.trip_id, user_id=current_user.user_id).first()
            if member is None:
                return error_response("NOT_FOUND", "요청한 자원을 찾을 수 없습니다.", 404)
            if ROLE_RANK[member.role] < ROLE_RANK[min_role]:
                return _forbidden()

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_planb_member(min_role="VIEWER"):
    """Like require_trip_member, but the route is keyed by planb_id
    (/api/planb/{planbId}, 7.3.5절)."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from ..models.planb import PlanB
            from ..models.trip_member import TripMember

            if not current_user.is_authenticated:
                return error_response("UNAUTHORIZED", "인증이 필요합니다.", 401)

            planb_id = kwargs.get("planb_id")
            planb = PlanB.query.filter_by(planb_id=planb_id).first()
            if planb is None:
                return error_response("NOT_FOUND", "요청한 자원을 찾을 수 없습니다.", 404)

            member = TripMember.query.filter_by(
                trip_id=planb.schedule.trip_id, user_id=current_user.user_id
            ).first()
            if member is None:
                return error_response("NOT_FOUND", "요청한 자원을 찾을 수 없습니다.", 404)
            if ROLE_RANK[member.role] < ROLE_RANK[min_role]:
                return _forbidden()

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_checklist_member(min_role="VIEWER"):
    """Like require_trip_member, but the route is keyed by check_id
    (/api/checklist/{checkId}, 7.3.6절)."""

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from ..models.checklist import Checklist
            from ..models.trip_member import TripMember

            if not current_user.is_authenticated:
                return error_response("UNAUTHORIZED", "인증이 필요합니다.", 401)

            check_id = kwargs.get("check_id")
            row = Checklist.query.filter_by(check_id=check_id).first()
            if row is None:
                return error_response("NOT_FOUND", "요청한 자원을 찾을 수 없습니다.", 404)

            member = TripMember.query.filter_by(trip_id=row.trip_id, user_id=current_user.user_id).first()
            if member is None:
                return error_response("NOT_FOUND", "요청한 자원을 찾을 수 없습니다.", 404)
            if ROLE_RANK[member.role] < ROLE_RANK[min_role]:
                return _forbidden()

            return fn(*args, **kwargs)

        return wrapper

    return decorator


def require_schedule_member(min_role="VIEWER"):
    """Like require_trip_member, but the route is keyed by schedule_id instead
    of trip_id (/api/schedules/{scheduleId}, 7.3.3절) — resolve the trip via
    the schedule first.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            from ..models.schedule import Schedule
            from ..models.trip_member import TripMember

            if not current_user.is_authenticated:
                return error_response("UNAUTHORIZED", "인증이 필요합니다.", 401)

            schedule_id = kwargs.get("schedule_id")
            schedule = Schedule.query.filter_by(schedule_id=schedule_id).first()
            if schedule is None:
                return error_response("NOT_FOUND", "요청한 자원을 찾을 수 없습니다.", 404)

            member = TripMember.query.filter_by(trip_id=schedule.trip_id, user_id=current_user.user_id).first()
            if member is None:
                return error_response("NOT_FOUND", "요청한 자원을 찾을 수 없습니다.", 404)
            if ROLE_RANK[member.role] < ROLE_RANK[min_role]:
                return _forbidden()

            return fn(*args, **kwargs)

        return wrapper

    return decorator
