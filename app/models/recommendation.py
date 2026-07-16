from datetime import datetime

from ..extensions import BigIntPK, db


class Recommendation(db.Model):
    __tablename__ = "RECOMMENDATION"

    rec_id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    trip_id = db.Column(db.BigInteger, db.ForeignKey("TRIP.trip_id", ondelete="CASCADE"), nullable=False)
    place_id = db.Column(db.BigInteger, db.ForeignKey("PLACE.place_id"), nullable=False)
    rec_type = db.Column(db.String(15), nullable=False)  # ATTRACTION / FOOD / CAFE / GAP_FILL / PLANB_ALT
    reason = db.Column(db.String(300), nullable=False)
    score = db.Column(db.Numeric(4, 3), nullable=False)
    is_accepted = db.Column(db.Boolean, nullable=True)  # NULL=미응답 (FR-306)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    place = db.relationship("Place")
