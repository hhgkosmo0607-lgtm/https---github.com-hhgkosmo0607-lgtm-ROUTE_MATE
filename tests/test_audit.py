import json
import logging


def _signup_and_login(client, email, nickname="user"):
    client.post("/api/auth/signup", json={"email": email, "password": "abcd1234", "nickname": nickname})
    client.post("/api/auth/login", json={"email": email, "password": "abcd1234"})


def _events(caplog):
    out = []
    for record in caplog.records:
        if record.name != "routemate.audit":
            continue
        try:
            out.append(json.loads(record.getMessage()))
        except ValueError:
            pass
    return out


def test_login_success_and_failure_are_logged(client, caplog):
    client.post("/api/auth/signup", json={"email": "audit1@test.com", "password": "abcd1234", "nickname": "a"})

    with caplog.at_level(logging.INFO, logger="routemate.audit"):
        client.post("/api/auth/login", json={"email": "audit1@test.com", "password": "wrong1234"})
        client.post("/api/auth/login", json={"email": "audit1@test.com", "password": "abcd1234"})

    events = _events(caplog)
    logins = [e for e in events if e["event"] == "LOGIN"]
    assert any(e["result"] == "FAILURE" for e in logins)
    assert any(e["result"] == "SUCCESS" for e in logins)
    # 감사 로그에 비밀번호가 절대 남으면 안 된다
    assert all("wrong1234" not in json.dumps(e) and "abcd1234" not in json.dumps(e) for e in logins)


def test_logout_is_logged(client, caplog):
    _signup_and_login(client, "audit2@test.com")

    with caplog.at_level(logging.INFO, logger="routemate.audit"):
        client.post("/api/auth/logout")

    events = _events(caplog)
    assert any(e["event"] == "LOGOUT" for e in events)


def test_trip_delete_is_logged(client, caplog):
    _signup_and_login(client, "audit3@test.com")
    trip_id = client.post(
        "/api/trips",
        json={"title": "여행", "start_date": "2026-09-01", "end_date": "2026-09-02", "region": "서울"},
    ).get_json()["data"]["trip_id"]

    with caplog.at_level(logging.INFO, logger="routemate.audit"):
        client.delete(f"/api/trips/{trip_id}")

    events = _events(caplog)
    assert any(e["event"] == "TRIP_DELETE" and e["trip_id"] == trip_id for e in events)


def test_access_denied_is_logged(client, caplog):
    _signup_and_login(client, "audit4owner@test.com")
    trip_id = client.post(
        "/api/trips",
        json={"title": "여행", "start_date": "2026-09-01", "end_date": "2026-09-02", "region": "서울"},
    ).get_json()["data"]["trip_id"]

    client.post("/api/auth/logout")
    _signup_and_login(client, "audit4viewer@test.com")
    client.post("/api/auth/logout")

    _signup_and_login(client, "audit4owner@test.com")
    client.post(f"/api/trips/{trip_id}/members", json={"email": "audit4viewer@test.com", "role": "VIEWER"})
    client.post("/api/auth/logout")

    _signup_and_login(client, "audit4viewer@test.com")
    with caplog.at_level(logging.INFO, logger="routemate.audit"):
        # VIEWER는 EDITOR 이상 권한이 필요한 수정 작업을 할 수 없다 → 403
        resp = client.put(f"/api/trips/{trip_id}", json={"title": "무단 변경"})

    assert resp.status_code == 403
    events = _events(caplog)
    assert any(e["event"] == "ACCESS_DENIED" for e in events)


def test_planb_activation_is_logged(client, caplog):
    _signup_and_login(client, "audit5@test.com")
    trip_id = client.post(
        "/api/trips",
        json={"title": "여행", "start_date": "2026-09-01", "end_date": "2026-09-03", "region": "서울"},
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
    schedule_id = client.get(f"/api/trips/{trip_id}/schedules").get_json()["data"]["schedules"][0]["schedule_id"]
    planb_id = client.post(
        f"/api/schedules/{schedule_id}/planb",
        json={"trigger_type": "MANUAL", "name": "대체", "category": "ATTRACTION", "lat": 37.567, "lng": 126.979},
    ).get_json()["data"]["planb_id"]

    with caplog.at_level(logging.INFO, logger="routemate.audit"):
        client.post(f"/api/planb/{planb_id}/confirm")

    events = _events(caplog)
    assert any(e["event"] == "PLANB_ACTIVATED" and e["planb_id"] == planb_id for e in events)
