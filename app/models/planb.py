from datetime import datetime

from ..extensions import BigIntPK, db


class PlanB(db.Model):
    __tablename__ = "PLAN_B"

    planb_id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    schedule_id = db.Column(db.BigInteger, db.ForeignKey("SCHEDULE.schedule_id", ondelete="CASCADE"), nullable=False)
    alt_place_id = db.Column(db.BigInteger, db.ForeignKey("PLACE.place_id"), nullable=False)
    trigger_type = db.Column(db.String(10), nullable=False)  # WAIT / CLOSED / RAIN / MANUAL
    priority = db.Column(db.SmallInteger, nullable=False, default=1)
    rain_threshold = db.Column(db.SmallInteger, nullable=True)
    status = db.Column(db.String(10), nullable=False, default="READY")  # READY/ACTIVATED/REJECTED/EXPIRED
    activated_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    schedule = db.relationship("Schedule", backref=db.backref("planb_options", cascade="all, delete-orphan"))
    alt_place = db.relationship("Place")

    __table_args__ = (db.UniqueConstraint("schedule_id", "priority", name="uq_planb_prio"),)
