from datetime import datetime

from ..extensions import db
from ..models.expense import Expense
from ..utils.response import ApiError
from . import trip_service

CATEGORIES = ("TRANSPORT", "STAY", "FOOD", "TICKET", "ETC")
ITEM_TYPES = ("BUDGET", "SPEND")


def add_expense(trip_id, user, category, item_type, amount, memo=None, spent_at=None):
    trip_service.get_trip_or_404(trip_id)

    if category not in CATEGORIES:
        raise ApiError("INVALID_INPUT", f"category는 {', '.join(CATEGORIES)} 중 하나여야 합니다.", 400)
    if item_type not in ITEM_TYPES:
        raise ApiError("INVALID_INPUT", "item_type은 BUDGET 또는 SPEND여야 합니다.", 400)
    if amount is None or amount < 0:
        raise ApiError("INVALID_INPUT", "amount는 0 이상이어야 합니다.", 400)

    row = Expense(
        trip_id=trip_id,
        category=category,
        item_type=item_type,
        amount=amount,
        memo=memo,
        spent_at=datetime.fromisoformat(spent_at) if spent_at else None,
        created_by=user.user_id,
    )
    db.session.add(row)
    db.session.commit()
    return row


def list_expenses(trip_id):
    trip_service.get_trip_or_404(trip_id)
    return Expense.query.filter_by(trip_id=trip_id).order_by(Expense.expense_id.desc()).all()


def summary(trip_id):
    """카테고리별 예산·지출 집계와 잔액 (FR-602)."""
    rows = list_expenses(trip_id)

    by_category = {c: {"budget": 0, "spend": 0} for c in CATEGORIES}
    for row in rows:
        key = "budget" if row.item_type == "BUDGET" else "spend"
        by_category[row.category][key] += row.amount

    result = []
    for category, totals in by_category.items():
        budget, spend = totals["budget"], totals["spend"]
        result.append(
            {
                "category": category,
                "budget": budget,
                "spend": spend,
                "remaining": budget - spend,
                "ratio": round(spend / budget, 3) if budget > 0 else None,
            }
        )

    total_budget = sum(r["budget"] for r in result)
    total_spend = sum(r["spend"] for r in result)
    return {
        "categories": result,
        "total_budget": total_budget,
        "total_spend": total_spend,
        "total_remaining": total_budget - total_spend,
    }
