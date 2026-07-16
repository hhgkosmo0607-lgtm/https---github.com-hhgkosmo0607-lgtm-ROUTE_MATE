"""Route Engine — 최적 경로 설계 (설계서 9.1절).

Flask/DB에 의존하지 않는 순수 Python 모듈이다 (4.3절 설계 원칙 ①).
좌표 간 이동시간·거리는 지도 API 대신 Haversine 근사(8.3절 폴백 정책)로 계산한다 —
지도 어댑터가 붙기 전까지 이 근사가 유일한 계산 방식이다.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import time

logger = logging.getLogger(__name__)

EARTH_RADIUS_KM = 6371.0
ROAD_FACTOR = 1.3  # 직선거리 보정 계수 (8.3절)
SPEED_KMH = {"WALK": 4, "TRANSIT": 20, "CAR": 40}  # 8.3절 수단별 평균 속도
TWO_OPT_MAX_ITER = 200  # 9.1.3절
EPSILON = 1e-9


@dataclass
class PlaceInput:
    place_id: int
    lat: float
    lng: float
    stay_min: int = 60


@dataclass
class ScheduleItem:
    place_id: int
    order_no: int
    start_min: int  # 자정 기준 분 단위 시각
    stay_min: int
    move_min: int | None = None
    move_km: float | None = None


@dataclass
class DayPlan:
    day_no: int
    items: list[ScheduleItem] = field(default_factory=list)


@dataclass
class RouteResult:
    days: list[DayPlan]
    unassigned: list[int]  # 미배치 보관함으로 이동한 place_id 목록 (FR-207)
    total_move_min: int
    total_move_km: float
    used_fallback: bool = True  # True면 Haversine 근사치 (8.3절 "근사치" 배지 표시용)


@dataclass
class DayItemInput:
    place_id: int
    lat: float
    lng: float
    stay_min: int
    is_locked: bool = False
    start_min: int | None = None  # 잠금 항목의 고정 시각 (자정 기준 분)


def haversine_km(lat1, lng1, lat2, lng2):
    r1, r2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(r1) * math.cos(r2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def build_distance_matrix(places, transport):
    """좌표 목록 → n×n 거리(km)/시간(분) 행렬 (9.1.2절 2단계, Haversine 근사)."""
    speed = SPEED_KMH[transport]
    n = len(places)
    dist_km = [[0.0] * n for _ in range(n)]
    time_min = [[0.0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            km = haversine_km(places[i].lat, places[i].lng, places[j].lat, places[j].lng) * ROAD_FACTOR
            dist_km[i][j] = km
            time_min[i][j] = km / speed * 60
    return dist_km, time_min


def _resolve_distance_matrix(places, transport, adapter):
    """어댑터가 있으면 실제 지도 API로, 실패하거나 없으면 Haversine 근사로 계산한다 (8.2/8.3절)."""
    if adapter is not None:
        coords = [(p.lat, p.lng) for p in places]
        try:
            duration_min, dist_km = adapter.distance_matrix(coords, transport)
            return dist_km, duration_min, False
        except Exception:
            logger.warning("map adapter distance_matrix failed, falling back to Haversine", exc_info=True)
    dist_km, time_min = build_distance_matrix(places, transport)
    return dist_km, time_min, True


def _nearest_neighbor(n, time_min, start=0):
    """3단계: 최근접 이웃 탐욕 선택으로 초기해를 만든다."""
    order = [start]
    remaining = set(range(n)) - {start}
    while remaining:
        cur = order[-1]
        nxt = min(remaining, key=lambda j: time_min[cur][j])
        order.append(nxt)
        remaining.remove(nxt)
    return order


def _segment_gain(order, i, k, time_min):
    a, b = order[i - 1], order[i]
    c, d = order[k], order[k + 1]
    return (time_min[a][b] + time_min[c][d]) - (time_min[a][c] + time_min[b][d])


def _two_opt(order, time_min):
    """4단계: 교차 구간 반전을 반복하여 총 이동시간을 줄인다 (개선 없거나 상한 200회)."""
    order = list(order)
    n = len(order)
    if n < 4:
        return order
    for _ in range(TWO_OPT_MAX_ITER):
        improved = False
        for i in range(1, n - 2):
            for k in range(i + 1, n - 1):
                if _segment_gain(order, i, k, time_min) > EPSILON:
                    order[i : k + 1] = reversed(order[i : k + 1])
                    improved = True
        if not improved:
            break
    return order


def _assemble_days(day_routes, places, dist_km, time_min, day_start_min):
    """확정된 Day별 방문 순서 → 시각·이동정보가 채워진 DayPlan 목록."""
    days = []
    total_move_min = 0
    total_move_km = 0.0

    for day_no, route in enumerate(day_routes, start=1):
        items = []
        cur_min = day_start_min
        prev = None
        for pos in route:
            place = places[pos]
            if prev is None:
                move_min, move_km = None, None
                arrival = cur_min
            else:
                move_min = round(time_min[prev][pos])
                move_km = round(dist_km[prev][pos], 2)
                arrival = cur_min + move_min
                total_move_min += move_min
                total_move_km += move_km
            items.append(
                ScheduleItem(
                    place_id=place.place_id,
                    order_no=len(items) + 1,
                    start_min=arrival,
                    stay_min=place.stay_min,
                    move_min=move_min,
                    move_km=move_km,
                )
            )
            cur_min = arrival + place.stay_min
            prev = pos
        days.append(DayPlan(day_no=day_no, items=items))

    return days, total_move_min, round(total_move_km, 2)


def _solve_with_optimizer(places, dist_km, time_min, total_days, day_start, day_end):
    """OR-Tools VRPTW 솔버로 Day 배치+순서를 동시 최적화. 실패 시 None."""
    from . import route_optimizer

    day_start_min = day_start.hour * 60 + day_start.minute
    day_end_min = day_end.hour * 60 + day_end.minute

    solved = route_optimizer.solve(places, time_min, dist_km, total_days, day_start_min, day_end_min)
    if solved is None:
        return None

    day_routes, unassigned = solved
    days, total_move_min, total_move_km = _assemble_days(day_routes, places, dist_km, time_min, day_start_min)
    return RouteResult(
        days=days, unassigned=unassigned, total_move_min=total_move_min, total_move_km=total_move_km
    )


def _assign_days(order, places, dist_km, time_min, total_days, day_start, day_end):
    """5~6단계: 일일 활동시간 한도 내에서 Day별로 순차 배치하고 시각을 부여한다 (9.1.4절)."""
    day_start_min = day_start.hour * 60 + day_start.minute
    day_end_min = day_end.hour * 60 + day_end.minute

    days: list[DayPlan] = []
    unassigned: list[int] = []
    day_no = 1
    items: list[ScheduleItem] = []
    cur_min = day_start_min
    prev_idx = None
    total_move_min = 0
    total_move_km = 0.0

    for pos in order:
        place = places[pos]

        if day_no > total_days:
            unassigned.append(place.place_id)
            continue

        if prev_idx is None:
            move_min, move_km = None, None
            arrival = cur_min
        else:
            move_min = round(time_min[prev_idx][pos])
            move_km = round(dist_km[prev_idx][pos], 2)
            arrival = cur_min + move_min
        finish = arrival + place.stay_min

        if finish > day_end_min and items:
            days.append(DayPlan(day_no=day_no, items=items))
            day_no += 1
            items = []
            cur_min = day_start_min
            prev_idx = None

            if day_no > total_days:
                unassigned.append(place.place_id)
                continue

            move_min, move_km = None, None
            arrival = cur_min
            finish = arrival + place.stay_min

        items.append(
            ScheduleItem(
                place_id=place.place_id,
                order_no=len(items) + 1,
                start_min=arrival,
                stay_min=place.stay_min,
                move_min=move_min,
                move_km=move_km,
            )
        )
        if move_min is not None:
            total_move_min += move_min
            total_move_km += move_km
        cur_min = finish
        prev_idx = pos

    if items:
        days.append(DayPlan(day_no=day_no, items=items))

    return RouteResult(
        days=days,
        unassigned=unassigned,
        total_move_min=total_move_min,
        total_move_km=round(total_move_km, 2),
    )


def build_route(places, transport, total_days, day_start=time(9, 0), day_end=time(21, 0), adapter=None):
    """장소 목록 → 최적화된 Day별 일정 (9.1.3절 의사코드 구현).

    places: PlaceInput 리스트. transport: WALK / TRANSIT / CAR.
    adapter: MapAdapter. 주어지면 실제 이동시간/거리를 조회하고, 실패 시 Haversine으로
    자동 폴백한다(8.2/8.3절). 생략하면 처음부터 Haversine만 사용한다.
    """
    if not places:
        return RouteResult(days=[], unassigned=[], total_move_min=0, total_move_km=0.0, used_fallback=True)

    if len(places) == 1:
        p = places[0]
        item = ScheduleItem(
            place_id=p.place_id,
            order_no=1,
            start_min=day_start.hour * 60 + day_start.minute,
            stay_min=p.stay_min,
        )
        return RouteResult(
            days=[DayPlan(day_no=1, items=[item])],
            unassigned=[],
            total_move_min=0,
            total_move_km=0.0,
            used_fallback=True,
        )

    dist_km, time_min, used_fallback = _resolve_distance_matrix(places, transport, adapter)

    # 1순위: OR-Tools VRPTW 솔버 (Day 배치·순서 동시 최적화, 실서비스 수준)
    try:
        result = _solve_with_optimizer(places, dist_km, time_min, total_days, day_start, day_end)
        if result is not None:
            result.used_fallback = used_fallback
            return result
    except Exception:
        logger.warning("route optimizer failed, falling back to NN+2-opt heuristic", exc_info=True)

    # 폴백: NN+2-opt 휴리스틱 (9.1.3절)
    order = _nearest_neighbor(len(places), time_min, start=0)
    order = _two_opt(order, time_min)
    result = _assign_days(order, places, dist_km, time_min, total_days, day_start, day_end)
    result.used_fallback = used_fallback
    return result


def recalc_day(items, transport, day_start=time(9, 0), adapter=None):
    """9.1.5절 부분 재계산 — 주어진 방문 순서는 그대로 두고 이동시간·시각만 다시 계산한다.

    잠금(is_locked) 항목은 자신의 start_min을 그대로 유지한 채 다음 항목의 기준
    시각으로만 사용된다 (FR-211). adapter가 주어지면 실제 이동시간을 조회하고,
    실패하면 Haversine으로 폴백한다(8.3절).
    """
    day_start_min = day_start.hour * 60 + day_start.minute
    result = []
    cur_min = day_start_min
    prev = None

    matrix = None
    if adapter is not None and len(items) > 1:
        coords = [(it.lat, it.lng) for it in items]
        try:
            duration_min, dist_km = adapter.distance_matrix(coords, transport)
            matrix = (duration_min, dist_km)
        except Exception:
            logger.warning("map adapter distance_matrix failed in recalc_day, falling back", exc_info=True)

    for idx, it in enumerate(items):
        if prev is None:
            move_min, move_km = None, None
        elif matrix is not None:
            move_min = round(matrix[0][idx - 1][idx])
            move_km = round(matrix[1][idx - 1][idx], 2)
        else:
            km = haversine_km(prev.lat, prev.lng, it.lat, it.lng) * ROAD_FACTOR
            move_min = round(km / SPEED_KMH[transport] * 60)
            move_km = round(km, 2)

        if it.is_locked and it.start_min is not None:
            arrival = it.start_min
        elif prev is None:
            arrival = cur_min
        else:
            arrival = cur_min + move_min

        result.append(
            ScheduleItem(
                place_id=it.place_id,
                order_no=idx + 1,
                start_min=arrival,
                stay_min=it.stay_min,
                move_min=move_min,
                move_km=move_km,
            )
        )
        cur_min = arrival + it.stay_min
        prev = it

    return result
