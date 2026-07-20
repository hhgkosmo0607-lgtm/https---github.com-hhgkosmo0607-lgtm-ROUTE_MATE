from flask import Blueprint, request
from flask_login import current_user, login_required, login_user, logout_user

from ..extensions import limiter
from ..services.auth_service import authenticate, request_password_reset, reset_password, signup
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


@auth_bp.post("/password-reset-request")
@limiter.limit("5 per minute")
def password_reset_request_route():
    body = request.get_json(silent=True) or {}
    request_password_reset(body.get("email"))
    # 계정 존재 여부와 무관하게 동일 응답 (존재 은닉)
    return success_response({"message": "가입된 이메일이라면 재설정 링크를 보냈습니다."})


@auth_bp.post("/password-reset")
@limiter.limit("5 per minute")
def password_reset_route():
    body = request.get_json(silent=True) or {}
    try:
        reset_password(body.get("token"), body.get("password"))
    except ApiError as e:
        return error_response(e.code, e.message, e.status)
    return success_response({"message": "비밀번호가 변경되었습니다. 새 비밀번호로 로그인해주세요."})
