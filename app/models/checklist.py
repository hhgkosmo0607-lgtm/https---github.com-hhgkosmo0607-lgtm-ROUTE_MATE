from ..extensions import BigIntPK, db


class Checklist(db.Model):
    __tablename__ = "CHECKLIST"

    check_id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    trip_id = db.Column(db.BigInteger, db.ForeignKey("TRIP.trip_id", ondelete="CASCADE"), nullable=False)
    item = db.Column(db.String(100), nullable=False)
    is_done = db.Column(db.Boolean, nullable=False, default=False)
    order_no = db.Column(db.SmallInteger, nullable=False)
    checked_by = db.Column(db.BigInteger, db.ForeignKey("USER.user_id"), nullable=True)

    checker = db.relationship("User")
