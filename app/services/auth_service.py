import re
from datetime import datetime, timedelta

from flask import current_app, url_for
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from ..extensions import db
from ..models.user import User
from ..utils.audit import log_event
from ..utils.mailer import send_email
from ..utils.response import ApiError

RESET_TOKEN_MAX_AGE = 3600  # 재설정 링크 유효 1시간

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PASSWORD_RE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{8,}$")  # 8자 이상, 영문+숫자 (FR-101)

LOGIN_FAIL_LIMIT = 5
LOCK_MINUTES = 5  # FR-102


def signup(email, password, nickname):
    email = (email or "").strip().lower()
    nickname = (nickname or "").strip()

    if not EMAIL_RE.match(email):
        raise ApiError("INVALID_INPUT", "이메일 형식이 올바르지 않습니다.")
    if not PASSWORD_RE.match(password or ""):
        raise ApiError("INVALID_INPUT", "비밀번호는 8자 이상이며 영문과 숫자를 포함해야 합니다.")
    if not nickname:
        raise ApiError("INVALID_INPUT", "닉네임을 입력해주세요.")
    if User.query.filter_by(email=email).first() is not None:
        raise ApiError("INVALID_INPUT", "이미 사용 중인 이메일입니다.")

    user = User(email=email, nickname=nickname)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return user


def authenticate(email, password):
    email = (email or "").strip().lower()
    user = User.query.filter_by(email=email).first()

    if user is None or user.deleted_at is not None:
        log_event("LOGIN", result="FAILURE", email=email)
        raise ApiError("UNAUTHORIZED", "이메일 또는 비밀번호가 올바르지 않습니다.", 401)

    if user.locked_until and user.locked_until > datetime.utcnow():
        log_event("LOGIN", user_id=user.user_id, result="LOCKED")
        raise ApiError("UNAUTHORIZED", "로그인 실패 횟수 초과로 계정이 잠시 잠겼습니다.", 401)

    if not user.check_password(password):
        user.login_fail_cnt += 1
        if user.login_fail_cnt >= LOGIN_FAIL_LIMIT:
            user.locked_until = datetime.utcnow() + timedelta(minutes=LOCK_MINUTES)
        db.session.commit()
        log_event("LOGIN", user_id=user.user_id, result="FAILURE")
        raise ApiError("UNAUTHORIZED", "이메일 또는 비밀번호가 올바르지 않습니다.", 401)

    user.login_fail_cnt = 0
    user.locked_until = None
    db.session.commit()
    log_event("LOGIN", user_id=user.user_id, result="SUCCESS")
    return user


def _reset_serializer():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="password-reset")


def make_reset_token(user):
    """비밀번호 해시 지문을 페이로드에 포함 — 비밀번호가 바뀌면 기존 토큰이 자동 무효화된다."""
    return _reset_serializer().dumps({"uid": user.user_id, "fp": user.password_hash[-12:]})


def request_password_reset(email):
    """재설정 링크 발송. 계정 존재 여부는 응답으로 노출하지 않는다(11.2절)."""
    email = (email or "").strip().lower()
    user = User.query.filter_by(email=email).first()
    if user is None or user.deleted_at is not None:
        log_event("PW_RESET_REQUEST", result="UNKNOWN_EMAIL", email=email)
        return

    token = make_reset_token(user)
    reset_url = url_for("views.reset_password_page", token=token, _external=True)
    send_email(
        user.email,
        "[RouteMate] 비밀번호 재설정 안내",
        f"아래 링크에서 비밀번호를 재설정하세요 (1시간 유효):\n\n{reset_url}\n\n"
        "요청하지 않았다면 이 메일을 무시하세요.",
    )
    log_event("PW_RESET_REQUEST", user_id=user.user_id, result="SENT")


def reset_password(token, new_password):
    try:
        payload = _reset_serializer().loads(token, max_age=RESET_TOKEN_MAX_AGE)
    except SignatureExpired:
        raise ApiError("INVALID_INPUT", "재설정 링크가 만료되었습니다. 다시 요청해주세요.", 400)
    except BadSignature:
        raise ApiError("INVALID_INPUT", "유효하지 않은 재설정 링크입니다.", 400)

    user = db.session.get(User, payload.get("uid"))
    if user is None or user.deleted_at is not None or user.password_hash[-12:] != payload.get("fp"):
        raise ApiError("INVALID_INPUT", "유효하지 않은 재설정 링크입니다.", 400)

    if not PASSWORD_RE.match(new_password or ""):
        raise ApiError("INVALID_INPUT", "비밀번호는 8자 이상이며 영문과 숫자를 포함해야 합니다.", 400)

    user.set_password(new_password)
    user.login_fail_cnt = 0
    user.locked_until = None
    db.session.commit()
    log_event("PW_RESET", user_id=user.user_id, result="SUCCESS")
    return user
