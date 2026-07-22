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


def test_nearby_global_geocode_result_ranked_before_bbox_poi(client, app, monkeypatch):
    from app.adapters.dto import PlaceDTO
    from app.services import place_service as svc

    app.config["MAP_ADAPTER_ENABLED"] = True

    def fake_geocode(self, query, country_codes="kr", limit=5):
        return [
            PlaceDTO(
                name="경복궁", lat=37.5796, lng=126.9770, address="서울 종로구",
                ext_id="1", osm_category="tourism", osm_type="attraction",
            )
        ]

    def fake_nearby_pois(self, south, west, north, east, limit=80, keyword=None, tag_filter=None):
        return [PlaceDTO(name="경복궁 맛집", lat=37.58, lng=126.977, ext_id="2", osm_category="amenity", osm_type="restaurant")]

    monkeypatch.setattr(svc.OSMAdapter, "geocode", fake_geocode)
    monkeypatch.setattr(svc.OSMAdapter, "nearby_pois", fake_nearby_pois)

    _signup_and_login(client, "gyeongbok@test.com")
    # bbox는 경복궁과 무관한 부산 인근 — 지도 화면 밖에서도 검색돼야 한다는 시나리오
    resp = client.get("/api/places/nearby?south=35.0&west=129.0&north=35.01&east=129.01&q=경복궁")

    assert resp.status_code == 200
    places = resp.get_json()["data"]["places"]
    assert places[0]["name"] == "경복궁"  # 전역 지오코딩 결과가 맨 위
    assert any(p["name"] == "경복궁 맛집" for p in places)  # 화면 bbox POI도 함께 포함


def test_nearby_global_geocode_survives_too_wide_bbox(client, app, monkeypatch):
    from app.adapters.dto import PlaceDTO
    from app.services import place_service as svc

    app.config["MAP_ADAPTER_ENABLED"] = True

    def fake_geocode(self, query, country_codes="kr", limit=5):
        return [PlaceDTO(name="경복궁", lat=37.5796, lng=126.9770, address="서울 종로구", ext_id="1")]

    def boom(self, *args, **kwargs):
        raise AssertionError("bbox가 너무 넓으면 Overpass 조회는 건너뛰어야 한다")

    monkeypatch.setattr(svc.OSMAdapter, "geocode", fake_geocode)
    monkeypatch.setattr(svc.OSMAdapter, "nearby_pois", boom)

    _signup_and_login(client, "widezoom@test.com")
    # 지도를 많이 축소한 상태(넓은 bbox) — 화면 POI 조회는 스킵하되 전역 검색은 살아있어야 한다
    resp = client.get("/api/places/nearby?south=33.0&west=124.0&north=39.0&east=132.0&q=경복궁")

    assert resp.status_code == 200
    data = resp.get_json()["data"]
    assert data["places"][0]["name"] == "경복궁"
    assert data["need_zoom"] is False


def test_search_does_not_append_region_to_query(client, app, monkeypatch):
    # 여행 지역이 부산이어도 "경복궁"은 그대로 질의돼야 한다 (예전엔 "경복궁 부산"으로
    # 붙여 0건이 되던 버그). geocode에 전달된 실제 질의어를 확인한다.
    from app.adapters.dto import PlaceDTO
    from app.services import place_service as svc

    app.config["MAP_ADAPTER_ENABLED"] = True
    captured = {}

    def fake_geocode(self, query, country_codes="kr", limit=5):
        captured["query"] = query
        return [PlaceDTO(name="경복궁", lat=37.5796, lng=126.9770, osm_category="tourism", osm_type="attraction")]

    monkeypatch.setattr(svc.OSMAdapter, "geocode", fake_geocode)

    _signup_and_login(client, "regionquery@test.com")
    resp = client.get("/api/places/search?q=경복궁&region=부산")

    assert resp.status_code == 200
    assert captured["query"] == "경복궁"  # 지역이 붙지 않은 순수 검색어
    assert resp.get_json()["data"]["places"][0]["name"] == "경복궁"
