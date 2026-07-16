from datetime import datetime

from ..extensions import BigIntPK, db

UNASSIGNED_DAY = 0  # 미배치 보관함 (Route Engine 실행 전 / FR-207)


class Schedule(db.Model):
    __tablename__ = "SCHEDULE"

    schedule_id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    trip_id = db.Column(db.BigInteger, db.ForeignKey("TRIP.trip_id", ondelete="CASCADE"), nullable=False)
    place_id = db.Column(db.BigInteger, db.ForeignKey("PLACE.place_id"), nullable=False)
    original_place_id = db.Column(db.BigInteger, db.ForeignKey("PLACE.place_id"), nullable=True)
    day_no = db.Column(db.SmallInteger, nullable=False, default=UNASSIGNED_DAY)
    order_no = db.Column(db.SmallInteger, nullable=False)
    start_time = db.Column(db.Time, nullable=True)
    stay_min = db.Column(db.SmallInteger, nullable=False, default=60)
    move_min = db.Column(db.SmallInteger, nullable=True)
    move_km = db.Column(db.Numeric(6, 2), nullable=True)
    is_locked = db.Column(db.Boolean, nullable=False, default=False)
    memo = db.Column(db.Text, nullable=True)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    place = db.relationship("Place", foreign_keys=[place_id])

    __table_args__ = (db.UniqueConstraint("trip_id", "day_no", "order_no", name="uq_sched_order"),)
