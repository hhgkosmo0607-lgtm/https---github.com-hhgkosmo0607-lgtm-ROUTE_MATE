from datetime import time

from app.engines import route_engine as re


def _place(pid, lat, lng, stay=60):
    return re.PlaceInput(place_id=pid, lat=lat, lng=lng, stay_min=stay)


# 서울 시내 근접 좌표 5곳 (임의)
FIVE_PLACES = [
    _place(1, 37.5665, 126.9780),
    _place(2, 37.5512, 126.9882),
    _place(3, 37.5796, 126.9770),
    _place(4, 37.5326, 127.0246),
    _place(5, 37.5219, 127.0411),
]


def test_nearest_neighbor_visits_every_place_once():
    # TC-101: 모든 장소가 정확히 1회씩 방문 순서에 포함되어야 한다.
    dist_km, time_min = re.build_distance_matrix(FIVE_PLACES, "CAR")
    order = re._nearest_neighbor(len(FIVE_PLACES), time_min, start=0)
    assert sorted(order) == list(range(len(FIVE_PLACES)))
    assert len(order) == len(set(order))


def test_two_opt_never_increases_total_time():
    # TC-102: 2-opt 개선 후 총 이동시간은 감소하거나 최소한 동일해야 한다.
    dist_km, time_min = re.build_distance_matrix(FIVE_PLACES, "CAR")

    def total_time(order):
        return sum(time_min[order[i]][order[i + 1]] for i in range(len(order) - 1))

    # 일부러 비효율적인(교차가 있는) 순서를 입력으로 사용한다.
    crossed = [0, 3, 1, 4, 2]
    improved = re._two_opt(crossed, time_min)

    assert sorted(improved) == sorted(crossed)
    assert total_time(improved) <= total_time(crossed) + re.EPSILON


def test_day_assignment_splits_on_overflow():
    # TC-103: 체류+이동 합계가 하루 활동시간을 넘으면 다음 Day로 분할한다.
    places = [_place(i, 37.5665 + i * 0.01, 126.9780, stay=200) for i in range(4)]
    result = re.build_route(places, "CAR", total_days=4, day_start=time(9, 0), day_end=time(12, 0))

    assert result.unassigned == []
    assert len(result.days) >= 2
    for day in result.days:
        last_item = day.items[-1]
        assert last_item.start_min + last_item.stay_min <= 12 * 60 or len(day.items) == 1


def test_overflow_places_go_to_unassigned_bucket():
    # TC-105: 여행 일수보다 필요한 Day가 많으면 초과분은 미배치 보관함으로 이동한다.
    places = [_place(i, 37.5665 + i * 0.01, 126.9780, stay=300) for i in range(6)]
    result = re.build_route(places, "CAR", total_days=1, day_start=time(9, 0), day_end=time(21, 0))

    assert len(result.days) == 1
    assert len(result.unassigned) > 0
    placed_ids = {item.place_id for day in result.days for item in day.items}
    assert placed_ids | set(result.unassigned) == {p.place_id for p in places}


def test_single_place_has_no_movement():
    # TC-107: 장소 1개면 이동 없이 일정 1건만 생성된다.
    result = re.build_route([_place(1, 37.5, 127.0)], "CAR", total_days=1)
    assert len(result.days) == 1
    assert len(result.days[0].items) == 1
    assert result.days[0].items[0].move_min is None
    assert result.total_move_min == 0


def test_empty_places_returns_empty_result():
    result = re.build_route([], "CAR", total_days=3)
    assert result.days == []
    assert result.unassigned == []


def test_build_route_end_to_end_within_capacity():
    result = re.build_route(FIVE_PLACES, "TRANSIT", total_days=3, day_start=time(9, 0), day_end=time(21, 0))
    assert result.unassigned == []
    placed_ids = {item.place_id for day in result.days for item in day.items}
    assert placed_ids == {p.place_id for p in FIVE_PLACES}
    assert result.total_move_min >= 0
