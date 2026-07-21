from app.services import recommend_service as svc


def _signup_and_login(client, email, nickname="user"):
    client.post("/api/auth/signup", json={"email": email, "password": "abcd1234", "nickname": nickname})
    client.post("/api/auth/login", json={"email": email, "password": "abcd1234"})


ANCHOR = {"name": "경복궁", "category": "ATTRACTION", "lat": 37.5796, "lng": 126.9770}
FOOD_CANDIDATE = {"name": "경복궁 맛집", "category": "RESTAURANT", "lat": 37.5786, "lng": 126.9764}
CAFE_CANDIDATE = {"name": "경복궁 카페", "category": "CAFE", "lat": 37.5800, "lng": 126.9760}


def _trip_with_candidates(client, email):
    _signup_and_login(client, email)
    trip_id = client.post(
        "/api/trips",
        json={"title": "서울 여행", "start_date": "2026-09-01", "end_date": "2026-09-03", "region": "서울"},
    ).get_json()["data"]["trip_id"]

    client.post(f"/api/trips/{trip_id}/places", json=ANCHOR)
    food = client.post(f"/api/trips/{trip_id}/places", json=FOOD_CANDIDATE).get_json()["data"]
    cafe = client.post(f"/api/trips/{trip_id}/places", json=CAFE_CANDIDATE).get_json()["data"]

    # 앵커만 남기고 후보는 일정에서 빼서 "아직 일정에 없는 장소 후보" 상태로 만든다.
    client.delete(f"/api/trips/{trip_id}/places/{food['place_id']}")
    client.delete(f"/api/trips/{trip_id}/places/{cafe['place_id']}")
    return trip_id


def test_create_recommendations_finds_nearby_candidates(client):
    trip_id = _trip_with_candidates(client, "recuser@test.com")

    resp = client.post(f"/api/trips/{trip_id}/recommendations", json={"type": "FOOD"})
    assert resp.status_code == 201
    recs = resp.get_json()["data"]["recommendations"]
    assert len(recs) == 1
    assert recs[0]["place"]["name"] == "경복궁 맛집"
    assert 0 <= recs[0]["score"] <= 1


def test_create_recommendations_rejects_bad_type(client):
    trip_id = _trip_with_candidates(client, "badtype@test.com")
    resp = client.post(f"/api/trips/{trip_id}/recommendations", json={"type": "NOPE"})
    assert resp.status_code == 400


def test_create_recommendations_requires_anchor(client):
    _signup_and_login(client, "noanchor@test.com")
    trip_id = client.post(
        "/api/trips",
        json={"title": "빈 여행", "start_date": "2026-09-01", "end_date": "2026-09-02", "region": "서울"},
    ).get_json()["data"]["trip_id"]

    resp = client.post(f"/api/trips/{trip_id}/recommendations", json={"type": "CAFE"})
    assert resp.status_code == 400
    assert resp.get_json()["error"]["code"] == "INVALID_INPUT"


def test_accept_recommendation_adds_to_unassigned_schedule(client):
    trip_id = _trip_with_candidates(client, "accept@test.com")
    rec = client.post(f"/api/trips/{trip_id}/recommendations", json={"type": "CAFE"}).get_json()["data"][
        "recommendations"
    ][0]

    resp = client.post(f"/api/recommendations/{rec['rec_id']}/accept")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["recommendation"]["is_accepted"] is True

    schedules = client.get(f"/api/trips/{trip_id}/schedules").get_json()["data"]["schedules"]
    assert any(s["place"]["name"] == "경복궁 카페" for s in schedules)


def test_reject_then_accept_is_conflict(client):
    trip_id = _trip_with_candidates(client, "reject@test.com")
    rec = client.post(f"/api/trips/{trip_id}/recommendations", json={"type": "CAFE"}).get_json()["data"][
        "recommendations"
    ][0]

    resp = client.post(f"/api/recommendations/{rec['rec_id']}/reject")
    assert resp.status_code == 200
    assert resp.get_json()["data"]["recommendation"]["is_accepted"] is False

    resp = client.post(f"/api/recommendations/{rec['rec_id']}/accept")
    assert resp.status_code == 409


def test_recommendation_uses_gemini_score_and_reason_when_configured(client, app, monkeypatch):
    app.config["GEMINI_API_KEY"] = "fake-key"

    def fake_score_candidates(self, candidates, profile, anchor, transport, count=5):
        return [{"place_id": candidates[0].place_id, "score": 91, "reason": "제미나이가 생성한 추천 이유"}]

    monkeypatch.setattr(svc.GeminiAdapter, "score_candidates", fake_score_candidates)

    trip_id = _trip_with_candidates(client, "gemini-ok@test.com")
    resp = client.post(f"/api/trips/{trip_id}/recommendations", json={"type": "CAFE"})

    assert resp.status_code == 201
    rec = resp.get_json()["data"]["recommendations"][0]
    assert rec["reason"] == "제미나이가 생성한 추천 이유"
    assert rec["score"] == 0.91


def test_recommendation_falls_back_to_rule_based_when_gemini_fails(client, app, monkeypatch):
    app.config["GEMINI_API_KEY"] = "fake-key"

    def boom(self, *args, **kwargs):
        raise RuntimeError("quota exceeded")

    monkeypatch.setattr(svc.GeminiAdapter, "score_candidates", boom)

    trip_id = _trip_with_candidates(client, "gemini-fail@test.com")
    resp = client.post(f"/api/trips/{trip_id}/recommendations", json={"type": "CAFE"})

    assert resp.status_code == 201
    rec = resp.get_json()["data"]["recommendations"][0]
    assert "근접도를 반영한 기본 추천" in rec["reason"]


def test_non_member_cannot_see_recommendations(client):
    trip_id = _trip_with_candidates(client, "owner4@test.com")
    client.post(f"/api/trips/{trip_id}/recommendations", json={"type": "FOOD"})

    client.post("/api/auth/logout")
    _signup_and_login(client, "outsider2@test.com")

    assert client.get(f"/api/trips/{trip_id}/recommendations").status_code == 404
