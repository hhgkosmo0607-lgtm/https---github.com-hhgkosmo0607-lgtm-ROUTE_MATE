from datetime import datetime, time

from ..extensions import BigIntPK, db


class Trip(db.Model):
    __tablename__ = "TRIP"

    trip_id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    owner_id = db.Column(db.BigInteger, db.ForeignKey("USER.user_id"), nullable=False)
    title = db.Column(db.String(100), nullable=False)
    start_date = db.Column(db.Date, nullable=False)
    end_date = db.Column(db.Date, nullable=False)
    region = db.Column(db.String(50), nullable=False)
    day_start = db.Column(db.Time, nullable=False, default=time(9, 0))
    day_end = db.Column(db.Time, nullable=False, default=time(21, 0))
    status = db.Column(db.String(10), nullable=False, default="PLANNING")
    share_token = db.Column(db.String(32), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    deleted_at = db.Column(db.DateTime, nullable=True)

    owner = db.relationship("User")
    members = db.relationship("TripMember", backref="trip", cascade="all, delete-orphan")
    schedules = db.relationship("Schedule", backref="trip", cascade="all, delete-orphan")

    __table_args__ = (db.CheckConstraint("end_date >= start_date", name="ck_trip_dates"),)
