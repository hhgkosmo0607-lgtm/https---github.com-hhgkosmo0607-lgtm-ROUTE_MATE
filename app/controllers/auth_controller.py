from flask import Blueprint, request
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import limiter
from ..services.auth_service import authenticate, signup
from ..utils.audit import log_event
from ..utils.response import ApiError, error_response, success_response

auth_bp = Blueprint("auth", __name__)


@auth_bp.post("/signup")
def signup_route():
    body = request.get_json(silent=True) or {}
    try:
        user = signup(body.get("email"), body.get("password"), body.get("nickname"))
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"user_id": user.user_id, "email": user.email, "nickname": user.nickname}, 201)


@auth_bp.post("/login")
@limiter.limit("10 per minute")  # 11.2절: IP 기준 로그인 레이트 리밋
def login_route():
    body = request.get_json(silent=True) or {}
    try:
        user = authenticate(body.get("email"), body.get("password"))
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    login_user(user)
    return success_response({"user_id": user.user_id, "email": user.email, "nickname": user.nickname})


@auth_bp.post("/logout")
@login_required
def logout_route():
    log_event("LOGOUT", user_id=current_user.user_id)
    logout_user()
    return success_response(None)
