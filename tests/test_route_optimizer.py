"""OR-Tools VRPTW 솔버 경로의 구조적 정합성 테스트."""

import random
from datetime import time

from app.engines import route_engine as re


def _random_places(n, seed=42):
    rng = random.Random(seed)
    return [
        re.PlaceInput(i, 37.45 + rng.random() * 0.25, 126.85 + rng.random() * 0.35, stay_min=rng.choice([45, 60, 90]))
        for i in range(n)
    ]


def test_solver_result_is_valid_partition():
    # 모든 장소는 정확히 한 번씩 — Day 배치 또는 미배치 보관함 중 한 곳에만 나타난다.
    places = _random_places(20)
    result = re.build_route(places, "CAR", total_days=3, day_start=time(9, 0), day_end=time(21, 0))

    placed = [item.place_id for day in result.days for item in day.items]
    all_ids = placed + result.unassigned
    assert sorted(all_ids) == sorted(p.place_id for p in places)
    assert len(placed) == len(set(placed))


def test_solver_respects_day_time_window():
    # 각 일정의 체류 종료 시각이 활동시간(day_end)을 넘지 않아야 한다.
    places = _random_places(20, seed=7)
    day_start, day_end = time(9, 0), time(18, 0)
    result = re.build_route(places, "CAR", total_days=3, day_start=day_start, day_end=day_end)

    day_end_min = day_end.hour * 60
    for day in result.days:
        for item in day.items:
            assert item.start_min + item.stay_min <= day_end_min, (
                f"place {item.place_id} finishes at {item.start_min + item.stay_min} > {day_end_min}"
            )


def test_solver_order_and_move_fields_consistent():
    places = _random_places(12, seed=9)
    result = re.build_route(places, "CAR", total_days=2)

    for day in result.days:
        assert [it.order_no for it in day.items] == list(range(1, len(day.items) + 1))
        assert day.items[0].move_min is None and day.items[0].move_km is None
        for it in day.items[1:]:
            assert it.move_min is not None and it.move_min >= 0
            assert it.move_km is not None and it.move_km >= 0


def test_solver_not_worse_than_heuristic():
    # 동일 입력에서 솔버가 휴리스틱보다 나쁜 해를 내면 안 된다 (같은 커버리지 기준).
    places = _random_places(20, seed=3)
    dist_km, time_min = re.build_distance_matrix(places, "CAR")

    order = re._nearest_neighbor(len(places), time_min)
    order = re._two_opt(order, time_min)
    heuristic = re._assign_days(order, places, dist_km, time_min, 3, time(9, 0), time(21, 0))

    solver = re._solve_with_optimizer(places, dist_km, time_min, 3, time(9, 0), time(21, 0))
    assert solver is not None
    assert len(solver.unassigned) <= len(heuristic.unassigned)
    if len(solver.unassigned) == len(heuristic.unassigned):
        assert solver.total_move_min <= heuristic.total_move_min


def test_heuristic_fallback_when_solver_unavailable(monkeypatch):
    # 솔버 임포트/실행 실패 시에도 build_route는 휴리스틱으로 정상 결과를 낸다 (8.3절 폴백).
    def boom(*args, **kwargs):
        raise RuntimeError("solver unavailable")

    monkeypatch.setattr(re, "_solve_with_optimizer", boom)

    places = _random_places(8)
    result = re.build_route(places, "CAR", total_days=2)
    placed = [item.place_id for day in result.days for item in day.items]
    assert sorted(placed + result.unassigned) == sorted(p.place_id for p in places)
