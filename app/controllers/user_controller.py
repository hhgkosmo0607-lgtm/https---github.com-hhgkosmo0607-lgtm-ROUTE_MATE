from datetime import datetime

from flask import Blueprint, request
from flask_login import current_user, login_required

from ..extensions import db
from ..models.profile import Profile
from ..utils.audit import log_event
from ..utils.response import error_response, success_response

user_bp = Blueprint("users", __name__)

PROFILE_FIELDS = ("travel_style", "food_pref", "allergy", "transport", "walk_level", "budget_level", "interests")


def _user_payload(user):
    return {"user_id": user.user_id, "email": user.email, "nickname": user.nickname}


def _profile_payload(profile):
    if profile is None:
        return None
    return {field: getattr(profile, field) for field in PROFILE_FIELDS}


@user_bp.get("/me")
@login_required
def get_me():
    return success_response(_user_payload(current_user))


@user_bp.put("/me")
@login_required
def update_me():
    body = request.get_json(silent=True) or {}
    nickname = body.get("nickname")
    password = body.get("password")

    if nickname:
        current_user.nickname = nickname.strip()
    if password:
        if len(password) < 8:
            return error_response("INVALID_INPUT", "비밀번호는 8자 이상이어야 합니다.", 400)
        current_user.set_password(password)

    db.session.commit()
    return success_response(_user_payload(current_user))


@user_bp.delete("/me")
@login_required
def delete_me():
    log_event("USER_DELETE", user_id=current_user.user_id)
    current_user.deleted_at = datetime.utcnow()
    db.session.commit()
    return success_response(None)


@user_bp.get("/me/profile")
@login_required
def get_profile():
    return success_response(_profile_payload(current_user.profile))


@user_bp.put("/me/profile")
@login_required
def update_profile():
    body = request.get_json(silent=True) or {}
    profile = current_user.profile
    if profile is None:
        profile = Profile(user_id=current_user.user_id)
        db.session.add(profile)

    for field in PROFILE_FIELDS:
        if field in body:
            setattr(profile, field, body[field])

    db.session.commit()
    return success_response(_profile_payload(profile))
