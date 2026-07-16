def _signup_and_login(client, email, nickname="user"):
    client.post("/api/auth/signup", json={"email": email, "password": "abcd1234", "nickname": nickname})
    client.post("/api/auth/login", json={"email": email, "password": "abcd1234"})


def _create_trip(client, **overrides):
    body = {"title": "제주 여행", "start_date": "2026-08-01", "end_date": "2026-08-03", "region": "제주"}
    body.update(overrides)
    return client.post("/api/trips", json=body)


def test_create_and_list_trip(client):
    _signup_and_login(client, "owner@test.com")

    resp = _create_trip(client)
    assert resp.status_code == 201
    trip = resp.get_json()["data"]
    assert trip["title"] == "제주 여행"
    assert trip["day_start"] == "09:00"
    assert trip["status"] == "PLANNING"

    resp = client.get("/api/trips")
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]["trips"]) == 1


def test_create_trip_rejects_end_before_start(client):
    _signup_and_login(client, "baddate@test.com")
    resp = _create_trip(client, start_date="2026-08-03", end_date="2026-08-01")
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_INPUT"


def test_non_member_gets_404_not_403(client):
    _signup_and_login(client, "a@test.com")
    trip_id = _create_trip(client).get_json()["data"]["trip_id"]

    client.post("/api/auth/logout")
    _signup_and_login(client, "b@test.com")

    assert client.get(f"/api/trips/{trip_id}").status_code == 404
    assert client.put(f"/api/trips/{trip_id}", json={"title": "변경 시도"}).status_code == 404
    assert client.delete(f"/api/trips/{trip_id}").status_code == 404


def test_add_and_remove_place(client):
    _signup_and_login(client, "place@test.com")
    trip_id = _create_trip(client).get_json()["data"]["trip_id"]

    resp = client.post(
        f"/api/trips/{trip_id}/places",
        json={"name": "해운대", "category": "ATTRACTION", "lat": 35.1587, "lng": 129.1604},
    )
    assert resp.status_code == 201
    place = resp.get_json()["data"]
    assert place["name"] == "해운대"

    resp = client.delete(f"/api/trips/{trip_id}/places/{place['place_id']}")
    assert resp.status_code == 200

    # removing again fails: the schedule link is gone (FR-203)
    resp = client.delete(f"/api/trips/{trip_id}/places/{place['place_id']}")
    assert resp.status_code == 404


def test_update_trip_fields(client):
    _signup_and_login(client, "editor@test.com")
    trip_id = _create_trip(client).get_json()["data"]["trip_id"]

    resp = client.put(f"/api/trips/{trip_id}", json={"title": "수정된 제목", "day_start": "08:00"})
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["title"] == "수정된 제목"
    assert data["day_start"] == "08:00"


def test_delete_trip_is_soft_delete(client):
    _signup_and_login(client, "del@test.com")
    trip_id = _create_trip(client).get_json()["data"]["trip_id"]

    assert client.delete(f"/api/trips/{trip_id}").status_code == 200
    assert client.get(f"/api/trips/{trip_id}").status_code == 404
    assert client.get("/api/trips").get_json()["data"]["trips"] == []


SEOUL_PLACES = [
    {"name": "경복궁", "category": "ATTRACTION", "lat": 37.5796, "lng": 126.9770},
    {"name": "명동", "category": "SHOPPING", "lat": 37.5636, "lng": 126.9834},
    {"name": "남산타워", "category": "ATTRACTION", "lat": 37.5512, "lng": 126.9882},
    {"name": "홍대", "category": "CAFE", "lat": 37.5563, "lng": 126.9236},
]


def test_generate_route_requires_places_first(client):
    _signup_and_login(client, "noplace@test.com")
    trip_id = _create_trip(client).get_json()["data"]["trip_id"]

    resp = client.post(f"/api/trips/{trip_id}/route", json={})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_INPUT"


def test_generate_route_rejects_bad_transport(client):
    _signup_and_login(client, "badtransport@test.com")
    trip_id = _create_trip(client).get_json()["data"]["trip_id"]
    client.post(f"/api/trips/{trip_id}/places", json=SEOUL_PLACES[0])

    resp = client.post(f"/api/trips/{trip_id}/route", json={"transport": "TELEPORT"})
    assert resp.status_code == 400


def test_generate_route_creates_day_schedules(client):
    _signup_and_login(client, "route@test.com")
    trip_id = _create_trip(client).get_json()["data"]["trip_id"]

    for place in SEOUL_PLACES:
        resp = client.post(f"/api/trips/{trip_id}/places", json=place)
        assert resp.status_code == 201

    resp = client.post(f"/api/trips/{trip_id}/route", json={"transport": "CAR"})
    assert resp.status_code == 200
    data = resp.get_json()["data"]

    assert data["total_days"] == 3
    assert data["unassigned_count"] == 0
    assert data["total_move_min"] >= 0
    placed = [s for day in data["days"] for s in day["schedules"]]
    assert len(placed) == len(SEOUL_PLACES)
    assert placed[0]["move_min"] is None  # 각 Day 첫 일정은 이동시간 없음

    resp = client.get(f"/api/trips/{trip_id}/schedules")
    assert resp.status_code == 200
    schedules = resp.get_json()["data"]["schedules"]
    assert len(schedules) == len(SEOUL_PLACES)
    assert all(s["day_no"] >= 1 for s in schedules)


def test_regenerating_route_replaces_previous_schedules(client):
    _signup_and_login(client, "regen@test.com")
    trip_id = _create_trip(client).get_json()["data"]["trip_id"]
    for place in SEOUL_PLACES[:2]:
        client.post(f"/api/trips/{trip_id}/places", json=place)

    client.post(f"/api/trips/{trip_id}/route", json={"transport": "WALK"})
    first_count = len(client.get(f"/api/trips/{trip_id}/schedules").get_json()["data"]["schedules"])

    client.post(f"/api/trips/{trip_id}/route", json={"transport": "WALK"})
    second_count = len(client.get(f"/api/trips/{trip_id}/schedules").get_json()["data"]["schedules"])

    assert first_count == second_count == 2
