from ..extensions import BigIntPK, db


class Expense(db.Model):
    __tablename__ = "EXPENSE"

    expense_id = db.Column(BigIntPK, primary_key=True, autoincrement=True)
    trip_id = db.Column(db.BigInteger, db.ForeignKey("TRIP.trip_id", ondelete="CASCADE"), nullable=False)
    category = db.Column(db.String(20), nullable=False)  # TRANSPORT/STAY/FOOD/TICKET/ETC
    item_type = db.Column(db.String(10), nullable=False)  # BUDGET / SPEND
    amount = db.Column(db.Integer, nullable=False)
    memo = db.Column(db.String(200), nullable=True)
    spent_at = db.Column(db.DateTime, nullable=True)
    created_by = db.Column(db.BigInteger, db.ForeignKey("USER.user_id"), nullable=False)

    creator = db.relationship("User")

    __table_args__ = (db.CheckConstraint("amount >= 0", name="ck_expense_amount"),)
