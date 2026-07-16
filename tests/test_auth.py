def test_signup_and_login(client):
    resp = client.post(
        "/api/auth/signup", json={"email": "a@test.com", "password": "abcd1234", "nickname": "tester"}
    )
    assert resp.status_code == 201
    assert resp.get_json()["data"]["email"] == "a@test.com"

    resp = client.post("/api/auth/login", json={"email": "a@test.com", "password": "abcd1234"})
    assert resp.status_code == 200
    assert resp.get_json()["success"] is True


def test_signup_duplicate_email_rejected(client):
    client.post("/api/auth/signup", json={"email": "dup@test.com", "password": "abcd1234", "nickname": "a"})
    resp = client.post("/api/auth/signup", json={"email": "dup@test.com", "password": "abcd1234", "nickname": "b"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_INPUT"


def test_signup_weak_password_rejected(client):
    resp = client.post(
        "/api/auth/signup", json={"email": "weak@test.com", "password": "abcdefgh", "nickname": "a"}
    )
    assert resp.status_code == 400


def test_login_locks_after_five_failures(client):
    client.post("/api/auth/signup", json={"email": "lock@test.com", "password": "abcd1234", "nickname": "a"})

    for _ in range(5):
        resp = client.post("/api/auth/login", json={"email": "lock@test.com", "password": "wrongpass1"})
        assert resp.status_code == 401

    resp = client.post("/api/auth/login", json={"email": "lock@test.com", "password": "abcd1234"})
    assert resp.status_code == 401
    assert "잠" in resp.get_json()["error"]["message"]


def test_me_requires_login(client):
    resp = client.get("/api/users/me")
    assert resp.status_code == 401


def test_logout_invalidates_session(client):
    client.post("/api/auth/signup", json={"email": "lo@test.com", "password": "abcd1234", "nickname": "a"})
    client.post("/api/auth/login", json={"email": "lo@test.com", "password": "abcd1234"})
    assert client.get("/api/users/me").status_code == 200

    client.post("/api/auth/logout")
    assert client.get("/api/users/me").status_code == 401


def test_csrf_missing_token_is_rejected(client):
    resp = client.raw.post(
        "/api/auth/signup", json={"email": "csrf@test.com", "password": "abcd1234", "nickname": "a"}
    )
    assert resp.status_code == 403


def test_profile_update_and_fetch(client):
    client.post("/api/auth/signup", json={"email": "p@test.com", "password": "abcd1234", "nickname": "a"})
    client.post("/api/auth/login", json={"email": "p@test.com", "password": "abcd1234"})

    resp = client.put(
        "/api/users/me/profile",
        json={"travel_style": "FOOD", "allergy": ["갑각류"], "transport": "WALK", "walk_level": 1},
    )
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["travel_style"] == "FOOD"
    assert data["allergy"] == ["갑각류"]

    resp = client.get("/api/users/me/profile")
    assert resp.get_json()["data"]["transport"] == "WALK"
