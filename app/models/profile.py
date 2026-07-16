from datetime import datetime

from ..extensions import BigIntPK, db
from .types import EncryptedJSON


class Profile(db.Model):
    __tablename__ = "PROFILE"

    profile_id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    user_id = db.Column(db.BigInteger, db.ForeignKey("USER.user_id"), unique=True, nullable=False)

    travel_style = db.Column(db.String(20), nullable=False, default="BALANCED")
    food_pref = db.Column(db.JSON, nullable=True)
    allergy = db.Column(EncryptedJSON, nullable=True)  # 11.3절: 건강 민감정보, AES-256-GCM 암호화 저장
    transport = db.Column(db.String(10), nullable=False, default="TRANSIT")
    walk_level = db.Column(db.SmallInteger, nullable=False, default=2)
    budget_level = db.Column(db.SmallInteger, nullable=False, default=3)
    interests = db.Column(db.JSON, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
