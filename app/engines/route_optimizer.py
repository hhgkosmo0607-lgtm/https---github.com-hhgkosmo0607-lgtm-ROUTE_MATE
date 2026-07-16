"""OR-Tools 기반 경로 최적화 솔버 (실서비스 수준 업그레이드).

설계서 9.1절의 NN+2-opt는 "전체 순회 최적화 → 탐욕적 Day 분할" 2단계라서
Day 경계에서 동선이 어긋나는 근본 한계가 있다. 이 모듈은 문제를 VRPTW
(시간창 있는 차량 경로 문제)로 모델링해 Day 배치와 방문 순서를 동시에
최적화한다:

- Day = 차량, 일일 활동시간(day_start~day_end) = 시간창
- 각 장소의 도착 시각 창 = [0, 활동시간 - 체류시간] → 체류 종료가 활동시간 안에
  들어오도록 강제. 체류시간이 활동시간을 넘는 장소는 창이 [0, 0]이 되어
  하루의 첫 일정으로만 배치된다 (기존 휴리스틱과 동일한 관용).
- 배치 불가 장소는 페널티를 물고 드롭 → 미배치 보관함 (FR-207)
- 탐색: PATH_CHEAPEST_ARC 초기해 + GUIDED_LOCAL_SEARCH, 시간 제한 내 종료 (NFR-06)

솔버 실패·미설치 시 호출부(route_engine.build_route)가 NN+2-opt 휴리스틱으로
폴백한다.
"""

from __future__ import annotations

import logging

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

logger = logging.getLogger(__name__)

DROP_PENALTY = 10**7  # 장소 드롭 페널티(초) — 어떤 이동시간 절감보다 크게


def _time_limit_sec(n):
    """문제 크기에 맞춘 탐색 시간. n=30에서도 NFR-06(3초) 이내."""
    return 1 if n <= 12 else 2


def solve(places, time_min, dist_km, total_days, day_start_min, day_end_min):
    """VRPTW 최적화. 성공 시 (day_routes, unassigned_ids) 반환, 해 없음이면 None.

    day_routes: [[place index, ...], ...] — Day 순서대로, 빈 Day는 제거됨.
    time_min/dist_km: n×n 행렬 (분/킬로미터).
    """
    n = len(places)
    day_minutes = day_end_min - day_start_min
    depot = n  # 가상 시작/종료 노드 (모든 연결 비용 0 → open route)

    manager = pywrapcp.RoutingIndexManager(n + 1, total_days, depot)
    routing = pywrapcp.RoutingModel(manager)

    def _sec(minutes):
        return int(round(minutes * 60))

    def transit_cb(from_index, to_index):
        """이동시간 + 출발 노드 체류시간(초). depot 연결은 0."""
        i = manager.IndexToNode(from_index)
        j = manager.IndexToNode(to_index)
        if i == depot or j == depot:
            return 0
        return _sec(time_min[i][j]) + _sec(places[i].stay_min)

    transit_index = routing.RegisterTransitCallback(transit_cb)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_index)

    routing.AddDimension(
        transit_index,
        0,  # 대기(slack) 없음 — 도착 즉시 체류 시작
        _sec(day_minutes),
        True,  # 각 Day의 시각은 0(=day_start)에서 시작
        "Time",
    )
    time_dim = routing.GetDimensionOrDie("Time")

    for idx in range(n):
        node = manager.NodeToIndex(idx)
        # 체류 종료가 활동시간 안에 들어오도록 도착 시각 상한을 조인다.
        # 체류가 활동시간보다 긴 장소는 상한 0 → 하루의 첫 일정으로만 허용.
        latest_arrival = max(0, day_minutes - places[idx].stay_min)
        time_dim.CumulVar(node).SetRange(0, _sec(latest_arrival))
        routing.AddDisjunction([node], DROP_PENALTY)

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    params.local_search_metaheuristic = routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    params.time_limit.FromSeconds(_time_limit_sec(n))
    params.log_search = False

    solution = routing.SolveWithParameters(params)
    if solution is None:
        logger.warning("OR-Tools solver returned no solution (n=%d, days=%d)", n, total_days)
        return None

    day_routes = []
    assigned = set()
    for vehicle in range(total_days):
        index = routing.Start(vehicle)
        route = []
        while not routing.IsEnd(index):
            node = manager.IndexToNode(index)
            if node != depot:
                route.append(node)
                assigned.add(node)
            index = solution.Value(routing.NextVar(index))
        if route:
            day_routes.append(route)

    unassigned = [places[i].place_id for i in range(n) if i not in assigned]
    return day_routes, unassigned
