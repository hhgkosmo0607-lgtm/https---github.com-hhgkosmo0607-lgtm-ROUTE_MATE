def _signup_and_login(client, email, nickname="user"):
    client.post("/api/auth/signup", json={"email": email, "password": "abcd1234", "nickname": nickname})
    return client.post("/api/auth/login", json={"email": email, "password": "abcd1234"})


def test_login_rate_limited_after_ten_per_minute(client):
    client.post("/api/auth/signup", json={"email": "rl@test.com", "password": "abcd1234", "nickname": "a"})

    statuses = []
    for _ in range(11):
        resp = client.post("/api/auth/login", json={"email": "rl@test.com", "password": "wrongpass1"})
        statuses.append(resp.status_code)

    assert statuses[-1] == 429
    assert statuses.count(401) == 10


def test_recommendation_rate_limited_after_three_per_minute(client):
    _signup_and_login(client, "rlrec@test.com")
    trip_id = client.post(
        "/api/trips",
        json={"title": "여행", "start_date": "2026-09-01", "end_date": "2026-09-02", "region": "서울"},
    ).get_json()["data"]["trip_id"]
    client.post(
        f"/api/trips/{trip_id}/places",
        json={"name": "장소1", "category": "ATTRACTION", "lat": 37.5665, "lng": 126.9780},
    )

    statuses = []
    for _ in range(4):
        resp = client.post(f"/api/trips/{trip_id}/recommendations", json={"type": "FOOD"})
        statuses.append(resp.status_code)

    assert statuses[-1] == 429
    assert client.get(f"/api/trips/{trip_id}/recommendations").status_code == 200  # 다른 엔드포인트는 영향 없음


def test_security_headers_present(client):
    resp = client.get("/")
    assert resp.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp.headers.get("X-Frame-Options") == "DENY"
    csp = resp.headers.get("Content-Security-Policy")
    assert csp is not None
    assert "script-src 'self' 'nonce-" in csp
    assert "default-src 'self'" in csp


def test_two_requests_get_different_csp_nonces(client):
    csp1 = client.get("/").headers.get("Content-Security-Policy")
    csp2 = client.get("/").headers.get("Content-Security-Policy")
    assert csp1 != csp2
