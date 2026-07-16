"""코드 검수에서 발견된 결함들의 회귀 테스트."""

SEOUL = [
    {"name": "경복궁", "category": "ATTRACTION", "lat": 37.5796, "lng": 126.9770},
    {"name": "명동", "category": "SHOPPING", "lat": 37.5636, "lng": 126.9834},
    {"name": "남산타워", "category": "ATTRACTION", "lat": 37.5512, "lng": 126.9882},
]


def _signup_and_login(client, email):
    client.post("/api/auth/signup", json={"email": email, "password": "abcd1234", "nickname": "u"})
    client.post("/api/auth/login", json={"email": email, "password": "abcd1234"})


def _trip_with_route(client, email):
    _signup_and_login(client, email)
    trip_id = client.post(
        "/api/trips",
        json={"title": "검수", "start_date": "2026-09-01", "end_date": "2026-09-03", "region": "서울"},
    ).get_json()["data"]["trip_id"]
    for p in SEOUL:
        client.post(f"/api/trips/{trip_id}/places", json=p)
    client.post(f"/api/trips/{trip_id}/route", json={"transport": "CAR"})
    return trip_id


def _schedules(client, trip_id):
    return client.get(f"/api/trips/{trip_id}/schedules").get_json()["data"]["schedules"]


def test_regenerate_route_with_locked_schedule_no_collision(client):
    # 결함 1: 잠긴 일정을 유지한 채 재생성하면 UNIQUE(trip_id, day_no, order_no) 충돌로 500
    trip_id = _trip_with_route(client, "lockregen@test.com")
    locked = _schedules(client, trip_id)[0]
    client.put(f"/api/schedules/{locked['schedule_id']}", json={"is_locked": True})

    resp = client.post(f"/api/trips/{trip_id}/route", json={"transport": "CAR"})
    assert resp.status_code == 200

    after = _schedules(client, trip_id)
    still_locked = next(s for s in after if s["schedule_id"] == locked["schedule_id"])
    assert still_locked["is_locked"] is True
    assert still_locked["day_no"] == locked["day_no"]
    assert still_locked["order_no"] == locked["order_no"]
    # 같은 Day 안에서 order_no 중복이 없어야 한다
    keys = [(s["day_no"], s["order_no"]) for s in after]
    assert len(keys) == len(set(keys))


def test_move_schedule_to_unassigned_bucket(client):
    # 결함 3: 프론트가 '미배치' 이동 옵션을 제공하지만 백엔드가 400으로 거부
    trip_id = _trip_with_route(client, "tobucket@test.com")
    target = _schedules(client, trip_id)[0]

    resp = client.put(
        f"/api/trips/{trip_id}/schedules/order",
        json={"schedule_id": target["schedule_id"], "day_no": 0, "order_no": 1},
    )
    assert resp.status_code == 200

    moved = next(s for s in _schedules(client, trip_id) if s["schedule_id"] == target["schedule_id"])
    assert moved["day_no"] == 0
    assert moved["start_time"] is None
    assert moved["move_min"] is None


def test_move_schedule_beyond_trip_days_rejected(client):
    # 결함 5: 여행 기간(3일)을 벗어난 Day로 이동 허용
    trip_id = _trip_with_route(client, "day99@test.com")
    target = _schedules(client, trip_id)[0]

    resp = client.put(
        f"/api/trips/{trip_id}/schedules/order",
        json={"schedule_id": target["schedule_id"], "day_no": 99, "order_no": 1},
    )
    assert resp.status_code == 400


def test_negative_stay_min_rejected(client):
    # 결함 4: 음수 체류시간 허용
    trip_id = _trip_with_route(client, "negstay@test.com")
    target = _schedules(client, trip_id)[0]

    for bad in (-100, 0, 99999, "abc", True):
        resp = client.put(f"/api/schedules/{target['schedule_id']}", json={"stay_min": bad})
        assert resp.status_code == 400, f"stay_min={bad!r} should be rejected"

    resp = client.put(f"/api/schedules/{target['schedule_id']}", json={"stay_min": 90})
    assert resp.status_code == 200


def test_duplicate_planb_priority_is_conflict(client):
    # 결함 2: Plan B 우선순위 중복 등록 시 IntegrityError로 500
    trip_id = _trip_with_route(client, "dupprio@test.com")
    schedule_id = _schedules(client, trip_id)[0]["schedule_id"]

    body = {"trigger_type": "MANUAL", "priority": 1, "name": "대체A", "category": "CAFE", "lat": 37.5, "lng": 127.0}
    assert client.post(f"/api/schedules/{schedule_id}/planb", json=body).status_code == 201

    body["name"] = "대체B"
    resp = client.post(f"/api/schedules/{schedule_id}/planb", json=body)
    assert resp.status_code == 409
    assert resp.get_json()["error"]["code"] == "CONFLICT"


def test_move_from_bucket_to_day_keeps_bucket_untimed(client):
    # _apply_day_recalc가 보관함(day 0)에 시각을 부여하던 부수 결함
    trip_id = _trip_with_route(client, "bucketstay@test.com")
    schedules = _schedules(client, trip_id)
    first, second = schedules[0], schedules[1]

    # 두 개를 보관함으로 보낸 뒤 하나만 다시 Day 1로
    client.put(f"/api/trips/{trip_id}/schedules/order", json={"schedule_id": first["schedule_id"], "day_no": 0, "order_no": 1})
    client.put(f"/api/trips/{trip_id}/schedules/order", json={"schedule_id": second["schedule_id"], "day_no": 0, "order_no": 2})
    client.put(f"/api/trips/{trip_id}/schedules/order", json={"schedule_id": first["schedule_id"], "day_no": 1, "order_no": 1})

    after = _schedules(client, trip_id)
    still_bucket = next(s for s in after if s["schedule_id"] == second["schedule_id"])
    assert still_bucket["day_no"] == 0
    assert still_bucket["start_time"] is None
    back_in_day = next(s for s in after if s["schedule_id"] == first["schedule_id"])
    assert back_in_day["day_no"] == 1
    assert back_in_day["start_time"] is not None
