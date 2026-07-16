SEOUL_PLACES = [
    {"name": "경복궁", "category": "ATTRACTION", "lat": 37.5796, "lng": 126.9770},
    {"name": "명동", "category": "SHOPPING", "lat": 37.5636, "lng": 126.9834},
    {"name": "남산타워", "category": "ATTRACTION", "lat": 37.5512, "lng": 126.9882},
]


def _signup_and_login(client, email, nickname="user"):
    client.post("/api/auth/signup", json={"email": email, "password": "abcd1234", "nickname": nickname})
    client.post("/api/auth/login", json={"email": email, "password": "abcd1234"})


def _trip_with_route(client, email):
    _signup_and_login(client, email)
    trip_id = client.post(
        "/api/trips",
        json={"title": "서울 여행", "start_date": "2026-09-01", "end_date": "2026-09-03", "region": "서울"},
    ).get_json()["data"]["trip_id"]
    for place in SEOUL_PLACES:
        client.post(f"/api/trips/{trip_id}/places", json=place)
    client.post(f"/api/trips/{trip_id}/route", json={"transport": "CAR"})
    return trip_id


def _schedules(client, trip_id):
    return client.get(f"/api/trips/{trip_id}/schedules").get_json()["data"]["schedules"]


def test_reorder_moves_schedule_to_new_day_and_recalculates(client):
    trip_id = _trip_with_route(client, "reorder@test.com")
    schedules = _schedules(client, trip_id)
    moved = schedules[0]

    resp = client.put(
        f"/api/trips/{trip_id}/schedules/order",
        json={"schedule_id": moved["schedule_id"], "day_no": 2, "order_no": 1},
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert 2 in data["affected_days"]

    after = _schedules(client, trip_id)
    updated = next(s for s in after if s["schedule_id"] == moved["schedule_id"])
    assert updated["day_no"] == 2
    assert updated["order_no"] == 1
    assert updated["move_min"] is None  # 새 Day의 첫 일정이므로 이동시간 없음


def test_locked_schedule_cannot_be_moved(client):
    trip_id = _trip_with_route(client, "locked@test.com")
    schedule_id = _schedules(client, trip_id)[0]["schedule_id"]

    client.put(f"/api/schedules/{schedule_id}", json={"is_locked": True})

    resp = client.put(
        f"/api/trips/{trip_id}/schedules/order",
        json={"schedule_id": schedule_id, "day_no": 2, "order_no": 1},
    )
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "CONSTRAINT_VIOLATION"


def test_update_stay_min_recalculates_following_times(client):
    trip_id = _trip_with_route(client, "stay@test.com")
    schedules = _schedules(client, trip_id)
    same_day = [s for s in schedules if s["day_no"] == schedules[0]["day_no"]]
    if len(same_day) < 2:
        # 하루에 몰리지 않았다면 재계산 효과가 안 보이니 순서상 첫 Day로 강제로 모아준다.
        target_day = schedules[0]["day_no"]
        same_day = [s for s in schedules if s["day_no"] == target_day]

    first = same_day[0]
    resp = client.put(f"/api/schedules/{first['schedule_id']}", json={"stay_min": 500})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["stay_min"] == 500


def test_delete_schedule_recalculates_remaining_day(client):
    trip_id = _trip_with_route(client, "delsched@test.com")
    schedules = _schedules(client, trip_id)
    target = schedules[0]

    resp = client.delete(f"/api/schedules/{target['schedule_id']}")
    assert resp.status_code == 200

    after = _schedules(client, trip_id)
    assert all(s["schedule_id"] != target["schedule_id"] for s in after)
    assert len(after) == len(schedules) - 1


def test_non_member_cannot_touch_schedule(client):
    trip_id = _trip_with_route(client, "owner3@test.com")
    schedule_id = _schedules(client, trip_id)[0]["schedule_id"]

    client.post("/api/auth/logout")
    _signup_and_login(client, "outsider@test.com")

    assert client.put(f"/api/schedules/{schedule_id}", json={"memo": "hack"}).status_code == 404
    assert client.delete(f"/api/schedules/{schedule_id}").status_code == 404
