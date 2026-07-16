from datetime import datetime

from ..extensions import BigIntPK, db


class TripMember(db.Model):
    __tablename__ = "TRIP_MEMBER"

    member_id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    trip_id = db.Column(db.BigInteger, db.ForeignKey("TRIP.trip_id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.BigInteger, db.ForeignKey("USER.user_id"), nullable=False)
    role = db.Column(db.String(10), nullable=False, default="OWNER")  # OWNER / EDITOR / VIEWER
    invited_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    user = db.relationship("User")

    __table_args__ = (db.UniqueConstraint("trip_id", "user_id", name="uq_trip_member"),)
