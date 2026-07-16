import re
from datetime import datetime, timedelta

from ..extensions import db
from ..models.user import User
from ..utils.audit import log_event
from ..utils.response import ApiError

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
