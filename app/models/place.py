from datetime import datetime

from ..extensions import BigIntPK, db


class Place(db.Model):
    __tablename__ = "PLACE"

    place_id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    ext_source = db.Column(db.String(10), nullable=False, default="USER")  # KAKAO / TOUR / USER
    ext_id = db.Column(db.String(64), nullable=True)
    name = db.Column(db.String(100), nullable=False)
    category = db.Column(db.String(30), nullable=False)  # ATTRACTION / RESTAURANT / CAFE / SHOPPING / ETC
    lat = db.Column(db.Numeric(10, 7), nullable=False)
    lng = db.Column(db.Numeric(10, 7), nullable=False)
    address = db.Column(db.String(200), nullable=True)
    open_info = db.Column(db.JSON, nullable=True)
    avg_stay_min = db.Column(db.SmallInteger, nullable=False, default=60)
    price_level = db.Column(db.SmallInteger, nullable=True)
    cached_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    __table_args__ = (db.UniqueConstraint("ext_source", "ext_id", name="uq_place_ext"),)
