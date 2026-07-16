from sqlalchemy import func

from ..extensions import db
from ..models.checklist import Checklist
from ..utils.response import ApiError
from . import trip_service

DEFAULT_TEMPLATE = ["여권/신분증", "충전기", "보조배터리", "상비약", "세면도구", "우산"]


def _next_order(trip_id):
    return (
        db.session.query(func.max(Checklist.order_no)).filter(Checklist.trip_id == trip_id).scalar() or 0
    ) + 1


def list_items(trip_id):
    """체크리스트 조회. 항목이 하나도 없으면 기본 템플릿을 시딩한다 (FR-601)."""
    trip_service.get_trip_or_404(trip_id)
    items = Checklist.query.filter_by(trip_id=trip_id).order_by(Checklist.order_no).all()
    if items:
        return items

    for order_no, name in enumerate(DEFAULT_TEMPLATE, start=1):
        db.session.add(Checklist(trip_id=trip_id, item=name, order_no=order_no))
    db.session.commit()
    return Checklist.query.filter_by(trip_id=trip_id).order_by(Checklist.order_no).all()


def add_item(trip_id, item):
    trip_service.get_trip_or_404(trip_id)
    if not item:
        raise ApiError("INVALID_INPUT", "item은 필수입니다.", 400)

    row = Checklist(trip_id=trip_id, item=item, order_no=_next_order(trip_id))
    db.session.add(row)
    db.session.commit()
    return row


def _get_or_404(check_id):
    row = Checklist.query.filter_by(check_id=check_id).first()
    if row is None:
        raise ApiError("NOT_FOUND", "체크리스트 항목을 찾을 수 없습니다.", 404)
    return row


def update_item(check_id, user, item=None, is_done=None):
    row = _get_or_404(check_id)
    if item is not None:
        row.item = item
    if is_done is not None:
        row.is_done = is_done
        row.checked_by = user.user_id if is_done else None
    db.session.commit()
    return row


def delete_item(check_id):
    row = _get_or_404(check_id)
    db.session.delete(row)
    db.session.commit()
