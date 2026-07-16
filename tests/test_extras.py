def _signup_and_login(client, email, nickname="user"):
    client.post("/api/auth/signup", json={"email": email, "password": "abcd1234", "nickname": nickname})
    client.post("/api/auth/login", json={"email": email, "password": "abcd1234"})


def _create_trip(client, **overrides):
    body = {"title": "제주 여행", "start_date": "2026-08-01", "end_date": "2026-08-03", "region": "제주"}
    body.update(overrides)
    return client.post("/api/trips", json=body).get_json()["data"]["trip_id"]


# ---- Checklist ----


def test_checklist_seeds_default_template_on_first_fetch(client):
    _signup_and_login(client, "check@test.com")
    trip_id = _create_trip(client)

    resp = client.get(f"/api/trips/{trip_id}/checklist")
    assert resp.status_code == 200
    items = resp.get_json()["data"]["checklist"]
    assert len(items) > 0
    assert all(i["is_done"] is False for i in items)


def test_checklist_add_and_toggle(client):
    _signup_and_login(client, "check2@test.com")
    trip_id = _create_trip(client)

    resp = client.post(f"/api/trips/{trip_id}/checklist", json={"item": "선크림"})
    assert resp.status_code == 201
    check_id = resp.get_json()["data"]["check_id"]

    resp = client.put(f"/api/checklist/{check_id}", json={"is_done": True})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["is_done"] is True

    resp = client.delete(f"/api/checklist/{check_id}")
    assert resp.status_code == 200


def test_checklist_requires_membership(client):
    _signup_and_login(client, "checkowner@test.com")
    trip_id = _create_trip(client)
    check_id = client.post(f"/api/trips/{trip_id}/checklist", json={"item": "여권"}).get_json()["data"]["check_id"]

    client.post("/api/auth/logout")
    _signup_and_login(client, "checkoutsider@test.com")

    assert client.put(f"/api/checklist/{check_id}", json={"is_done": True}).status_code == 404


# ---- Expense ----


def test_expense_add_and_summary(client):
    _signup_and_login(client, "exp@test.com")
    trip_id = _create_trip(client)

    client.post(f"/api/trips/{trip_id}/expenses", json={"category": "FOOD", "item_type": "BUDGET", "amount": 100000})
    client.post(f"/api/trips/{trip_id}/expenses", json={"category": "FOOD", "item_type": "SPEND", "amount": 30000})
    client.post(
        f"/api/trips/{trip_id}/expenses", json={"category": "TRANSPORT", "item_type": "BUDGET", "amount": 50000}
    )

    resp = client.get(f"/api/trips/{trip_id}/expenses/summary")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    food = next(c for c in data["categories"] if c["category"] == "FOOD")
    assert food["budget"] == 100000
    assert food["spend"] == 30000
    assert food["remaining"] == 70000
    assert data["total_budget"] == 150000
    assert data["total_spend"] == 30000


def test_expense_rejects_negative_amount(client):
    _signup_and_login(client, "expneg@test.com")
    trip_id = _create_trip(client)
    resp = client.post(
        f"/api/trips/{trip_id}/expenses", json={"category": "FOOD", "item_type": "SPEND", "amount": -100}
    )
    assert resp.status_code == 400


# ---- Share link ----


def test_share_link_lifecycle(client):
    _signup_and_login(client, "share@test.com")
    trip_id = _create_trip(client)
    client.post(
        f"/api/trips/{trip_id}/places",
        json={"name": "장소1", "category": "ATTRACTION", "lat": 37.5665, "lng": 126.9780},
    )

    resp = client.post(f"/api/trips/{trip_id}/share/link")
    assert resp.status_code == 200
    token = resp.get_json()["data"]["share_token"]
    assert len(token) == 32

    resp = client.get(f"/api/shared/{token}")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["title"] == "제주 여행"

    client.delete(f"/api/trips/{trip_id}/share/link")
    resp = client.get(f"/api/shared/{token}")
    assert resp.status_code == 404


def test_only_owner_can_create_share_link(client):
    _signup_and_login(client, "shareowner@test.com")
    trip_id = _create_trip(client)

    client.post("/api/auth/logout")
    _signup_and_login(client, "sharestranger@test.com")

    resp = client.post(f"/api/trips/{trip_id}/share/link")
    assert resp.status_code == 404  # 멤버가 아니므로 존재 자체를 숨김


# ---- Members ----


def test_invite_member_and_change_role(client):
    _signup_and_login(client, "owner6@test.com")
    trip_id = _create_trip(client)

    client.post("/api/auth/logout")
    _signup_and_login(client, "invitee@test.com")
    client.post("/api/auth/logout")

    _signup_and_login(client, "owner6@test.com")
    resp = client.post(f"/api/trips/{trip_id}/members", json={"email": "invitee@test.com", "role": "VIEWER"})
    assert resp.status_code == 201
    member = resp.get_json()["data"]
    assert member["role"] == "VIEWER"

    resp = client.put(f"/api/trips/{trip_id}/members/{member['user_id']}", json={"role": "EDITOR"})
    assert resp.status_code == 200
    assert resp.get_json()["data"]["role"] == "EDITOR"

    resp = client.get(f"/api/trips/{trip_id}/members")
    assert len(resp.get_json()["data"]["members"]) == 2


def test_invited_member_can_view_trip(client):
    _signup_and_login(client, "owner7@test.com")
    trip_id = _create_trip(client)

    client.post("/api/auth/logout")
    _signup_and_login(client, "member7@test.com")
    client.post("/api/auth/logout")

    _signup_and_login(client, "owner7@test.com")
    client.post(f"/api/trips/{trip_id}/members", json={"email": "member7@test.com", "role": "VIEWER"})
    client.post("/api/auth/logout")

    _signup_and_login(client, "member7@test.com")
    resp = client.get(f"/api/trips/{trip_id}")
    assert resp.status_code == 200

    # VIEWER는 수정 불가
    resp = client.put(f"/api/trips/{trip_id}", json={"title": "변경 시도"})
    assert resp.status_code == 403


def test_duplicate_invite_is_conflict(client):
    _signup_and_login(client, "owner8@test.com")
    trip_id = _create_trip(client)

    client.post("/api/auth/logout")
    _signup_and_login(client, "dup@test.com")
    client.post("/api/auth/logout")

    _signup_and_login(client, "owner8@test.com")
    client.post(f"/api/trips/{trip_id}/members", json={"email": "dup@test.com", "role": "VIEWER"})
    resp = client.post(f"/api/trips/{trip_id}/members", json={"email": "dup@test.com", "role": "EDITOR"})
    assert resp.status_code == 409


# ---- Clone ----


def test_clone_trip_copies_schedules(client):
    _signup_and_login(client, "clone@test.com")
    trip_id = _create_trip(client)
    client.post(
        f"/api/trips/{trip_id}/places",
        json={"name": "장소1", "category": "ATTRACTION", "lat": 37.5665, "lng": 126.9780},
    )
    client.post(f"/api/trips/{trip_id}/route", json={"transport": "CAR"})

    resp = client.post(f"/api/trips/{trip_id}/clone")
    assert resp.status_code == 201
    new_trip = resp.get_json()["data"]
    assert "복사본" in new_trip["title"]

    resp = client.get(f"/api/trips/{new_trip['trip_id']}/schedules")
    assert len(resp.get_json()["data"]["schedules"]) == 1

    trips = client.get("/api/trips").get_json()["data"]["trips"]
    assert len(trips) == 2
