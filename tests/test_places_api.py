def _signup_and_login(client, email):
    client.post("/api/auth/signup", json={"email": email, "password": "abcd1234", "nickname": "u"})
    client.post("/api/auth/login", json={"email": email, "password": "abcd1234"})


def test_nearby_requires_login(client):
    resp = client.get("/api/places/nearby?south=37.5&west=126.9&north=37.51&east=126.91")
    assert resp.status_code == 401


def test_nearby_returns_empty_when_adapter_disabled(client):
    # TestConfig는 외부 호출 차단(MAP_ADAPTER_ENABLED=false) — 빈 목록 폴백 (8.3절)
    _signup_and_login(client, "nearby@test.com")
    resp = client.get("/api/places/nearby?south=37.5&west=126.9&north=37.51&east=126.91")
    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["places"] == []


def test_nearby_handles_bad_params(client):
    _signup_and_login(client, "nearbybad@test.com")
    resp = client.get("/api/places/nearby?south=abc")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["places"] == []


def test_search_requires_login(client):
    resp = client.get("/api/places/search?q=경복궁")
    assert resp.status_code == 401
