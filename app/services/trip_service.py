import secrets
from datetime import datetime, time

from flask import current_app
from flask_login import current_user
from sqlalchemy import func

from ..adapters.osm_adapter import OSMAdapter
from ..engines import route_engine
from ..extensions import db
from ..models.place import Place
from ..models.schedule import UNASSIGNED_DAY, Schedule
from ..models.trip import Trip
from ..models.trip_member import TripMember
from ..models.user import User
from ..utils.audit import log_event
from ..utils.response import ApiError

DEFAULT_TRANSPORT = "TRANSIT"
MEMBER_ROLES = ("OWNER", "EDITOR", "VIEWER")


def create_trip(owner, title, start_date, end_date, region, day_start=None, day_end=None):
    if not title:
        raise ApiError("INVALID_INPUT", "여행 제목을 입력해주세요.")
    if not region:
        raise ApiError("INVALID_INPUT", "여행 지역을 입력해주세요.")
    if end_date < start_date:
        raise ApiError("INVALID_INPUT", "종료일은 시작일보다 빠를 수 없습니다.")

    trip = Trip(
        owner_id=owner.user_id,
        title=title,
        start_date=start_date,
        end_date=end_date,
        region=region,
        day_start=day_start or time(9, 0),
        day_end=day_end or time(21, 0),
        status="PLANNING",
    )
    db.session.add(trip)
    db.session.flush()

    db.session.add(TripMember(trip_id=trip.trip_id, user_id=owner.user_id, role="OWNER"))
    db.session.commit()
    return trip


def list_trips_for_user(user):
    return (
        Trip.query.join(TripMember, TripMember.trip_id == Trip.trip_id)
        .filter(TripMember.user_id == user.user_id, Trip.deleted_at.is_(None))
        .order_by(Trip.start_date)
        .all()
    )


def get_trip_or_404(trip_id):
    trip = Trip.query.filter_by(trip_id=trip_id).first()
    if trip is None or trip.deleted_at is not None:
        raise ApiError("NOT_FOUND", "여행을 찾을 수 없습니다.", 404)
    return trip


def update_trip(trip_id, **fields):
    trip = get_trip_or_404(trip_id)

    new_start = fields.get("start_date", trip.start_date)
    new_end = fields.get("end_date", trip.end_date)
    if new_end < new_start:
        raise ApiError("INVALID_INPUT", "종료일은 시작일보다 빠를 수 없습니다.")

    for key, value in fields.items():
        if value is not None:
            setattr(trip, key, value)
    db.session.commit()
    return trip


def delete_trip(trip_id):
    trip = get_trip_or_404(trip_id)
    trip.deleted_at = datetime.utcnow()
    db.session.commit()
    log_event("TRIP_DELETE", user_id=current_user.get_id(), trip_id=trip_id)


def add_place(trip_id, name, category, lat, lng, address=None):
    get_trip_or_404(trip_id)

    if not name or not category:
        raise ApiError("INVALID_INPUT", "name, category는 필수입니다.")

    place = Place(ext_source="USER", name=name, category=category, lat=lat, lng=lng, address=address)
    db.session.add(place)
    db.session.flush()

    max_order = (
        db.session.query(func.max(Schedule.order_no))
        .filter(Schedule.trip_id == trip_id, Schedule.day_no == UNASSIGNED_DAY)
        .scalar()
        or 0
    )
    schedule = Schedule(trip_id=trip_id, place_id=place.place_id, day_no=UNASSIGNED_DAY, order_no=max_order + 1)
    db.session.add(schedule)
    db.session.commit()
    return place, schedule


def remove_place(trip_id, place_id):
    get_trip_or_404(trip_id)
    schedule = Schedule.query.filter_by(trip_id=trip_id, place_id=place_id).first()
    if schedule is None:
        raise ApiError("NOT_FOUND", "일정에서 해당 장소를 찾을 수 없습니다.", 404)
    db.session.delete(schedule)
    db.session.commit()


def list_schedules(trip_id):
    get_trip_or_404(trip_id)
    return (
        Schedule.query.filter_by(trip_id=trip_id)
        .order_by(Schedule.day_no, Schedule.order_no)
        .all()
    )


def minutes_to_time(minutes):
    minutes %= 24 * 60
    return time(minutes // 60, minutes % 60)


def get_map_adapter():
    """8.1/8.2절: OSM(Nominatim+OSRM) 어댑터. 비활성화 시 None(순수 Haversine)."""
    if not current_app.config.get("MAP_ADAPTER_ENABLED"):
        return None
    return OSMAdapter(contact_email=current_app.config.get("MAP_CONTACT_EMAIL"))


def _apply_day_recalc(trip, day_no, ordered_schedules, transport=None):
    """9.1.5절 부분 재계산 — 주어진 순서로 한 Day의 이동시간·시각만 다시 계산해 저장한다.

    미배치 보관함(day 0)은 시각 개념이 없으므로 순번만 다시 매기고 시간 정보를 비운다.
    """
    if not ordered_schedules:
        return

    if day_no == UNASSIGNED_DAY:
        for s in ordered_schedules:
            s.day_no = UNASSIGNED_DAY
            s.order_no = -(s.schedule_id)
        db.session.flush()
        for idx, s in enumerate(ordered_schedules, start=1):
            s.order_no = idx
            s.start_time = None
            s.move_min = None
            s.move_km = None
        db.session.flush()
        return

    resolved_transport = transport or owner_transport(trip)
    inputs = [
        route_engine.DayItemInput(
            place_id=s.place_id,
            lat=float(s.place.lat),
            lng=float(s.place.lng),
            stay_min=s.stay_min,
            is_locked=s.is_locked,
            start_min=(s.start_time.hour * 60 + s.start_time.minute) if (s.is_locked and s.start_time) else None,
        )
        for s in ordered_schedules
    ]
    results = route_engine.recalc_day(inputs, resolved_transport, trip.day_start, adapter=get_map_adapter())

    # UNIQUE(trip_id, day_no, order_no) 충돌 없이 재배치하기 위해 임시 음수값을 거친다.
    for s in ordered_schedules:
        s.day_no = day_no
        s.order_no = -(s.schedule_id)
    db.session.flush()

    for s, r in zip(ordered_schedules, results):
        s.order_no = r.order_no
        s.start_time = minutes_to_time(r.start_min)
        s.move_min = r.move_min
        s.move_km = r.move_km
    db.session.flush()


def reorder_schedule(trip_id, schedule_id, day_no, order_no):
    """드래그 앤 드롭으로 순서·Day를 변경하고 영향받는 Day만 재계산한다 (FR-207/208)."""
    trip = get_trip_or_404(trip_id)
    schedule = Schedule.query.filter_by(trip_id=trip_id, schedule_id=schedule_id).first()
    if schedule is None:
        raise ApiError("NOT_FOUND", "일정을 찾을 수 없습니다.", 404)
    if schedule.is_locked:
        raise ApiError("CONSTRAINT_VIOLATION", "잠금된 일정은 이동할 수 없습니다.", 422)
    total_days = (trip.end_date - trip.start_date).days + 1
    if day_no < UNASSIGNED_DAY or day_no > total_days:
        raise ApiError("INVALID_INPUT", f"day_no는 0(미배치)부터 {total_days} 사이여야 합니다.", 400)

    old_day = schedule.day_no
    old_day_items = [
        s
        for s in Schedule.query.filter_by(trip_id=trip_id, day_no=old_day).order_by(Schedule.order_no).all()
        if s.schedule_id != schedule_id
    ]

    if day_no == old_day:
        new_day_items = old_day_items
    else:
        new_day_items = list(
            Schedule.query.filter_by(trip_id=trip_id, day_no=day_no).order_by(Schedule.order_no).all()
        )

    insert_at = max(0, min(order_no - 1, len(new_day_items)))
    new_day_items.insert(insert_at, schedule)

    affected = {day_no: new_day_items}
    if old_day != day_no:
        affected[old_day] = old_day_items

    for d, items in affected.items():
        _apply_day_recalc(trip, d, items)

    db.session.commit()
    return sorted(affected.keys())


def update_schedule(schedule_id, stay_min=None, memo=None, is_locked=None):
    """체류시간·메모·잠금 수정 (FR-209/211). 체류시간이 바뀌면 해당 Day만 재계산한다."""
    schedule = Schedule.query.filter_by(schedule_id=schedule_id).first()
    if schedule is None:
        raise ApiError("NOT_FOUND", "일정을 찾을 수 없습니다.", 404)
    trip = get_trip_or_404(schedule.trip_id)

    if stay_min is not None and (
        isinstance(stay_min, bool) or not isinstance(stay_min, int) or not 1 <= stay_min <= 24 * 60
    ):
        raise ApiError("INVALID_INPUT", "stay_min은 1~1440 사이의 정수여야 합니다.", 400)

    stay_changed = stay_min is not None and stay_min != schedule.stay_min
    if stay_min is not None:
        schedule.stay_min = stay_min
    if memo is not None:
        schedule.memo = memo
    if is_locked is not None:
        schedule.is_locked = is_locked

    if stay_changed and schedule.day_no != UNASSIGNED_DAY:
        day_items = (
            Schedule.query.filter_by(trip_id=schedule.trip_id, day_no=schedule.day_no)
            .order_by(Schedule.order_no)
            .all()
        )
        _apply_day_recalc(trip, schedule.day_no, day_items)

    db.session.commit()
    return schedule


def delete_schedule(schedule_id):
    """일정 삭제 + 재계산 (7.3.3절)."""
    schedule = Schedule.query.filter_by(schedule_id=schedule_id).first()
    if schedule is None:
        raise ApiError("NOT_FOUND", "일정을 찾을 수 없습니다.", 404)
    trip = get_trip_or_404(schedule.trip_id)
    day_no = schedule.day_no

    db.session.delete(schedule)
    db.session.flush()

    if day_no != UNASSIGNED_DAY:
        remaining = (
            Schedule.query.filter_by(trip_id=trip.trip_id, day_no=day_no).order_by(Schedule.order_no).all()
        )
        _apply_day_recalc(trip, day_no, remaining)

    db.session.commit()


def generate_route(trip_id, transport=None, day_start=None, day_end=None):
    """자동 경로 생성 — Route Engine 실행 (FR-204/205, 9.1절).

    잠긴 일정(is_locked)은 재계산에서 제외한다(FR-211). 그 외 일정은 전부
    삭제 후 Route Engine 결과로 다시 생성한다 (전체 재최적화).
    """
    trip = get_trip_or_404(trip_id)

    schedules = Schedule.query.filter_by(trip_id=trip_id, is_locked=False).all()
    if not schedules:
        raise ApiError("INVALID_INPUT", "경로를 생성할 장소가 없습니다.", 400)

    places = [
        route_engine.PlaceInput(
            place_id=s.place_id, lat=float(s.place.lat), lng=float(s.place.lng), stay_min=s.stay_min
        )
        for s in schedules
    ]
    total_days = (trip.end_date - trip.start_date).days + 1
    resolved_transport = transport or owner_transport(trip)

    result = route_engine.build_route(
        places,
        resolved_transport,
        total_days,
        day_start or trip.day_start,
        day_end or trip.day_end,
        adapter=get_map_adapter(),
    )

    for s in schedules:
        db.session.delete(s)
    db.session.flush()

    # 잠긴 일정은 유지되므로(FR-211) 그 자리(day_no, order_no)를 피해 배치해야
    # UNIQUE(trip_id, day_no, order_no) 충돌이 나지 않는다.
    locked_orders = {}
    for s in Schedule.query.filter_by(trip_id=trip_id, is_locked=True).all():
        locked_orders.setdefault(s.day_no, set()).add(s.order_no)
    order_counters = {}

    def _next_free_order(day_no):
        n = order_counters.get(day_no, 0) + 1
        while n in locked_orders.get(day_no, ()):
            n += 1
        order_counters[day_no] = n
        return n

    for day in result.days:
        for item in day.items:
            db.session.add(
                Schedule(
                    trip_id=trip_id,
                    place_id=item.place_id,
                    day_no=day.day_no,
                    order_no=_next_free_order(day.day_no),
                    start_time=minutes_to_time(item.start_min),
                    stay_min=item.stay_min,
                    move_min=item.move_min,
                    move_km=item.move_km,
                )
            )
    for place_id in result.unassigned:
        db.session.add(
            Schedule(trip_id=trip_id, place_id=place_id, day_no=UNASSIGNED_DAY, order_no=_next_free_order(UNASSIGNED_DAY))
        )

    db.session.commit()
    return total_days, result


GAP_MIN_MINUTES = 60  # FR-303: 이 이상 비면 추천 제안


def detect_gaps(trip_id):
    """일정 공백 감지 (FR-303). 각 Day에서 60분 이상 빈 구간을 찾는다.

    타임라인은 순차 배치라 중간 공백은 잠금 일정 주변에서만 생기고,
    대부분의 공백은 마지막 일정 이후 ~ 활동 종료 시각 사이다.
    """
    trip = get_trip_or_404(trip_id)
    day_end_min = trip.day_end.hour * 60 + trip.day_end.minute

    gaps = []
    by_day = {}
    for s in Schedule.query.filter_by(trip_id=trip_id).order_by(Schedule.day_no, Schedule.order_no).all():
        if s.day_no == UNASSIGNED_DAY or s.start_time is None:
            continue
        by_day.setdefault(s.day_no, []).append(s)

    for day_no, items in by_day.items():
        # 잠금 일정 앞의 중간 공백
        for prev, nxt in zip(items, items[1:]):
            prev_end = prev.start_time.hour * 60 + prev.start_time.minute + prev.stay_min
            nxt_start = nxt.start_time.hour * 60 + nxt.start_time.minute - (nxt.move_min or 0)
            if nxt_start - prev_end >= GAP_MIN_MINUTES:
                gaps.append(
                    {
                        "day_no": day_no,
                        "from": minutes_to_time(prev_end).strftime("%H:%M"),
                        "free_min": nxt_start - prev_end,
                        "near_schedule_id": prev.schedule_id,
                        "kind": "middle",
                    }
                )
        # 마지막 일정 이후 ~ 활동 종료
        last = items[-1]
        last_end = last.start_time.hour * 60 + last.start_time.minute + last.stay_min
        if day_end_min - last_end >= GAP_MIN_MINUTES:
            gaps.append(
                {
                    "day_no": day_no,
                    "from": minutes_to_time(last_end).strftime("%H:%M"),
                    "free_min": day_end_min - last_end,
                    "near_schedule_id": last.schedule_id,
                    "kind": "tail",
                }
            )
    return sorted(gaps, key=lambda g: (g["day_no"], g["from"]))


def owner_transport(trip):
    profile = trip.owner.profile
    if profile is not None and profile.transport:
        return profile.transport
    return DEFAULT_TRANSPORT


def generate_share_link(trip_id):
    """읽기 전용 공유 링크 생성/재발급 (FR-604)."""
    trip = get_trip_or_404(trip_id)
    trip.share_token = secrets.token_hex(16)
    db.session.commit()
    return trip.share_token


def revoke_share_link(trip_id):
    trip = get_trip_or_404(trip_id)
    trip.share_token = None
    db.session.commit()


def get_trip_by_share_token(token):
    trip = Trip.query.filter_by(share_token=token).first()
    if trip is None or trip.deleted_at is not None:
        raise ApiError("NOT_FOUND", "공유 링크를 찾을 수 없습니다.", 404)
    return trip


def list_members(trip_id):
    get_trip_or_404(trip_id)
    return TripMember.query.filter_by(trip_id=trip_id).all()


def invite_member(trip_id, email, role):
    """동반자 초대 (FR-605)."""
    get_trip_or_404(trip_id)
    if role not in MEMBER_ROLES:
        raise ApiError("INVALID_INPUT", f"role은 {', '.join(MEMBER_ROLES)} 중 하나여야 합니다.", 400)

    user = User.query.filter_by(email=(email or "").strip().lower()).first()
    if user is None or user.deleted_at is not None:
        raise ApiError("INVALID_INPUT", "초대할 회원을 찾을 수 없습니다.", 400)

    if TripMember.query.filter_by(trip_id=trip_id, user_id=user.user_id).first() is not None:
        raise ApiError("CONFLICT", "이미 여행에 참여 중인 회원입니다.", 409)

    member = TripMember(trip_id=trip_id, user_id=user.user_id, role=role)
    db.session.add(member)
    db.session.commit()
    return member


def update_member_role(trip_id, user_id, role):
    get_trip_or_404(trip_id)
    if role not in MEMBER_ROLES:
        raise ApiError("INVALID_INPUT", f"role은 {', '.join(MEMBER_ROLES)} 중 하나여야 합니다.", 400)

    member = TripMember.query.filter_by(trip_id=trip_id, user_id=user_id).first()
    if member is None:
        raise ApiError("NOT_FOUND", "여행 멤버를 찾을 수 없습니다.", 404)

    member.role = role
    db.session.commit()
    return member


def clone_trip(trip_id, owner):
    """여행 복제 — 기존 여행을 새 여행의 템플릿으로 사용한다 (FR-606)."""
    trip = get_trip_or_404(trip_id)

    new_trip = Trip(
        owner_id=owner.user_id,
        title=f"{trip.title} (복사본)",
        start_date=trip.start_date,
        end_date=trip.end_date,
        region=trip.region,
        day_start=trip.day_start,
        day_end=trip.day_end,
        status="PLANNING",
    )
    db.session.add(new_trip)
    db.session.flush()
    db.session.add(TripMember(trip_id=new_trip.trip_id, user_id=owner.user_id, role="OWNER"))

    for s in Schedule.query.filter_by(trip_id=trip_id).order_by(Schedule.day_no, Schedule.order_no).all():
        db.session.add(
            Schedule(
                trip_id=new_trip.trip_id,
                place_id=s.place_id,
                day_no=s.day_no,
                order_no=s.order_no,
                start_time=s.start_time,
                stay_min=s.stay_min,
                move_min=s.move_min,
                move_km=s.move_km,
            )
        )

    db.session.commit()
    return new_trip
