def _signup_and_login(client, email, nickname="user"):
    client.post("/api/auth/signup", json={"email": email, "password": "abcd1234", "nickname": nickname})
    client.post("/api/auth/login", json={"email": email, "password": "abcd1234"})


def _trip_with_two_schedules(client, email, day_start="09:00", day_end="21:00"):
    _signup_and_login(client, email)
    trip_id = client.post(
        "/api/trips",
        json={
            "title": "서울 여행",
            "start_date": "2026-09-01",
            "end_date": "2026-09-03",
            "region": "서울",
            "day_start": day_start,
            "day_end": day_end,
        },
    ).get_json()["data"]["trip_id"]

    client.post(
        f"/api/trips/{trip_id}/places",
        json={"name": "장소1", "category": "ATTRACTION", "lat": 37.5665, "lng": 126.9780},
    )
    client.post(
        f"/api/trips/{trip_id}/places",
        json={"name": "장소2", "category": "ATTRACTION", "lat": 37.5666, "lng": 126.9781},
    )
    client.post(f"/api/trips/{trip_id}/route", json={"transport": "CAR"})

    schedules = client.get(f"/api/trips/{trip_id}/schedules").get_json()["data"]["schedules"]
    return trip_id, schedules


def test_register_and_list_planb(client):
    trip_id, schedules = _trip_with_two_schedules(client, "reguser@test.com")
    target = schedules[0]

    resp = client.post(
        f"/api/schedules/{target['schedule_id']}/planb",
        json={"trigger_type": "WAIT", "name": "대체 장소", "category": "ATTRACTION", "lat": 37.567, "lng": 126.979},
    )
    assert resp.status_code == 201
    planb = resp.get_json()["data"]
    assert planb["status"] == "READY"
    assert planb["priority"] == 1

    resp = client.get(f"/api/schedules/{target['schedule_id']}/planb")
    assert resp.status_code == 200
    assert len(resp.get_json()["data"]["planb"]) == 1


def test_activate_is_non_destructive_then_confirm_applies_swap(client):
    trip_id, schedules = _trip_with_two_schedules(client, "activate@test.com")
    target = schedules[0]
    original_place_name = target["place"]["name"]

    planb_id = client.post(
        f"/api/schedules/{target['schedule_id']}/planb",
        json={"trigger_type": "MANUAL", "name": "대체 장소", "category": "ATTRACTION", "lat": 37.567, "lng": 126.979},
    ).get_json()["data"]["planb_id"]

    resp = client.post(f"/api/planb/{planb_id}/activate")
    assert resp.status_code == 200
    preview = resp.get_json()["data"]
    assert preview["replaced"]["from"] == original_place_name
    assert preview["replaced"]["to"] == "대체 장소"
    assert preview["confirm_url"] == f"/api/planb/{planb_id}/confirm"

    # activate는 미리보기일 뿐이므로 실제 일정은 아직 안 바뀌어 있어야 한다.
    still_original = client.get(f"/api/trips/{trip_id}/schedules").get_json()["data"]["schedules"]
    assert any(s["place"]["name"] == original_place_name for s in still_original)

    resp = client.post(f"/api/planb/{planb_id}/confirm")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["place"]["name"] == "대체 장소"

    after = client.get(f"/api/trips/{trip_id}/schedules").get_json()["data"]["schedules"]
    assert any(s["place"]["name"] == "대체 장소" for s in after)
    assert not any(s["place"]["name"] == original_place_name for s in after)


def test_confirm_twice_is_conflict(client):
    trip_id, schedules = _trip_with_two_schedules(client, "twice@test.com")
    target = schedules[0]
    planb_id = client.post(
        f"/api/schedules/{target['schedule_id']}/planb",
        json={"trigger_type": "MANUAL", "name": "대체", "category": "ATTRACTION", "lat": 37.567, "lng": 126.979},
    ).get_json()["data"]["planb_id"]

    client.post(f"/api/planb/{planb_id}/confirm")
    resp = client.post(f"/api/planb/{planb_id}/confirm")
    assert resp.status_code == 409


def test_revert_restores_original_place(client):
    trip_id, schedules = _trip_with_two_schedules(client, "revert@test.com")
    target = schedules[0]
    original_place_name = target["place"]["name"]
    planb_id = client.post(
        f"/api/schedules/{target['schedule_id']}/planb",
        json={"trigger_type": "MANUAL", "name": "대체", "category": "ATTRACTION", "lat": 37.567, "lng": 126.979},
    ).get_json()["data"]["planb_id"]
    client.post(f"/api/planb/{planb_id}/confirm")

    resp = client.post(f"/api/schedules/{target['schedule_id']}/revert")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["place"]["name"] == original_place_name


def test_confirm_blocks_overflow_until_explicitly_accepted(client):
    trip_id, schedules = _trip_with_two_schedules(client, "overflow@test.com", day_start="09:00", day_end="09:30")
    target = schedules[1]  # 두 번째 일정 — 대체 시 이동시간이 늘어나 초과를 유발한다.

    planb_id = client.post(
        f"/api/schedules/{target['schedule_id']}/planb",
        json={
            "trigger_type": "MANUAL",
            "name": "아주 먼 대체 장소",
            "category": "ATTRACTION",
            "lat": 38.4,
            "lng": 126.9780,
        },
    ).get_json()["data"]["planb_id"]

    resp = client.post(f"/api/planb/{planb_id}/confirm")
    assert resp.status_code == 422
    assert resp.get_json()["error"]["code"] == "CONSTRAINT_VIOLATION"

    resp = client.post(f"/api/planb/{planb_id}/confirm", json={"accept_overflow": True})
    assert resp.status_code == 200


def test_non_member_cannot_access_planb(client):
    trip_id, schedules = _trip_with_two_schedules(client, "owner5@test.com")
    target = schedules[0]
    planb_id = client.post(
        f"/api/schedules/{target['schedule_id']}/planb",
        json={"trigger_type": "MANUAL", "name": "대체", "category": "ATTRACTION", "lat": 37.567, "lng": 126.979},
    ).get_json()["data"]["planb_id"]

    client.post("/api/auth/logout")
    _signup_and_login(client, "outsider3@test.com")

    assert client.get(f"/api/schedules/{target['schedule_id']}/planb").status_code == 404
    assert client.post(f"/api/planb/{planb_id}/activate").status_code == 404
