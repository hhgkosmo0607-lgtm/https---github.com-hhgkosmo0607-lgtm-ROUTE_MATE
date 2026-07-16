from app.extensions import db
from app.models.profile import Profile
from app.utils.crypto import decrypt_json, encrypt_json


def test_encrypt_decrypt_roundtrip():
    token = encrypt_json(["갑각류", "땅콩"])
    assert token is not None
    assert "갑각류" not in token  # 평문이 그대로 노출되면 안 된다
    assert decrypt_json(token) == ["갑각류", "땅콩"]


def test_encrypt_json_handles_none():
    assert encrypt_json(None) is None
    assert decrypt_json(None) is None


def test_allergy_stored_encrypted_at_rest(app):
    with app.app_context():
        from app.models.user import User

        user = User(email="crypto@test.com", nickname="a")
        user.set_password("abcd1234")
        db.session.add(user)
        db.session.flush()

        profile = Profile(user_id=user.user_id, allergy=["갑각류"])
        db.session.add(profile)
        db.session.commit()

        raw = db.session.execute(
            db.text("SELECT allergy FROM PROFILE WHERE profile_id = :pid"), {"pid": profile.profile_id}
        ).scalar()
        assert raw is not None
        assert "갑각류" not in raw  # 원시 DB 컬럼 값에는 평문이 없어야 한다

        db.session.expire(profile)
        assert profile.allergy == ["갑각류"]  # ORM을 통하면 투명하게 복호화된다
