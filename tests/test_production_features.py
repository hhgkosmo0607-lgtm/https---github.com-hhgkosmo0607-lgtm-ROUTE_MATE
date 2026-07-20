"""실서비스 보완 기능 테스트 — 비밀번호 재설정, 캐시, 빈 시간 감지, healthz, 약관 페이지."""

import logging
import re
import time as clock

from app.utils.ttl_cache import TTLCache


def _signup_and_login(client, email):
    client.post("/api/auth/signup", json={"email": email, "password": "abcd1234", "nickname": "u"})
    client.post("/api/auth/login", json={"email": email, "password": "abcd1234"})


# ---- 비밀번호 재설정 ----


def test_password_reset_full_flow(client, caplog):
    client.post("/api/auth/signup", json={"email": "reset@test.com", "password": "abcd1234", "nickname": "a"})

    # 요청 → 개발 모드에서는 로그로 링크가 발송된다
    with caplog.at_level(logging.INFO, logger="app.utils.mailer"):
        resp = client.post("/api/auth/password-reset-request", json={"email": "reset@test.com"})
    assert resp.status_code == 200

    mail_logs = "\n".join(r.getMessage() for r in caplog.records if "DEV MAIL" in r.getMessage())
    match = re.search(r"token=([A-Za-z0-9._\-]+)", mail_logs)
    assert match, "재설정 링크가 메일(로그)에 포함되어야 한다"
    token = match.group(1)

    # 새 비밀번호로 변경
    resp = client.post("/api/auth/password-reset", json={"token": token, "password": "newpass99"})
    assert resp.status_code == 200

    # 새 비밀번호로 로그인 성공, 옛 비밀번호는 실패
    assert client.post("/api/auth/login", json={"email": "reset@test.com", "password": "newpass99"}).status_code == 200
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"email": "reset@test.com", "password": "abcd1234"}).status_code == 401

    # 사용된(비밀번호 변경 전) 토큰은 무효 — 해시 지문 불일치
    resp = client.post("/api/auth/password-reset", json={"token": token, "password": "another11"})
    assert resp.status_code == 400


def test_password_reset_unknown_email_does_not_leak(client):
    resp = client.post("/api/auth/password-reset-request", json={"email": "ghost@test.com"})
    assert resp.status_code == 200  # 존재 여부와 무관하게 동일 응답


def test_password_reset_rejects_bad_token(client):
    resp = client.post("/api/auth/password-reset", json={"token": "garbage", "password": "newpass99"})
    assert resp.status_code == 400


def test_password_reset_rejects_weak_password(client, caplog):
    client.post("/api/auth/signup", json={"email": "weakr@test.com", "password": "abcd1234", "nickname": "a"})
    with caplog.at_level(logging.INFO, logger="app.utils.mailer"):
        client.post("/api/auth/password-reset-request", json={"email": "weakr@test.com"})
    token = re.search(r"token=([A-Za-z0-9._\-]+)", "\n".join(r.getMessage() for r in caplog.records)).group(1)

    resp = client.post("/api/auth/password-reset", json={"token": token, "password": "onlyletters"})
    assert resp.status_code == 400


# ---- TTL 캐시 ----


def test_ttl_cache_set_get_and_expiry(monkeypatch):
    cache = TTLCache(maxsize=10)
    cache.set("k", "v", ttl=100)
    assert cache.get("k") == "v"

    t = clock.monotonic()
    monkeypatch.setattr(clock, "monotonic", lambda: t + 101)
    import app.utils.ttl_cache as mod

    monkeypatch.setattr(mod.time, "monotonic", lambda: t + 101)
    assert cache.get("k") is None


def test_ttl_cache_eviction_respects_maxsize():
    cache = TTLCache(maxsize=10)
    for i in range(15):
        cache.set(f"k{i}", i, ttl=1000)
    assert len(cache._store) <= 11  # maxsize 근처에서 유지 (10% 비우기)


def test_ttl_cache_get_or_set_calls_producer_once():
    cache = TTLCache()
    calls = []

    def producer():
        calls.append(1)
        return "value"

    assert cache.get_or_set("x", 100, producer) == "value"
    assert cache.get_or_set("x", 100, producer) == "value"
    assert len(calls) == 1


# ---- 빈 시간 감지 (FR-303) ----


def test_gaps_detects_free_tail_time(client):
    _signup_and_login(client, "gaps@test.com")
    trip_id = client.post(
        "/api/trips",
        json={"title": "여행", "start_date": "2026-09-01", "end_date": "2026-09-02", "region": "서울"},
    ).get_json()["data"]["trip_id"]
    client.post(
        f"/api/trips/{trip_id}/places",
        json={"name": "장소1", "category": "ATTRACTION", "lat": 37.5665, "lng": 126.9780},
    )
    client.post(f"/api/trips/{trip_id}/route", json={"transport": "CAR"})

    resp = client.get(f"/api/trips/{trip_id}/gaps")
    assert resp.status_code == 200
    gaps = resp.get_json()["data"]["gaps"]
    # 09:00~10:00 체류 후 21:00까지 비므로 tail 공백이 감지되어야 한다
    assert any(g["kind"] == "tail" and g["free_min"] >= 60 for g in gaps)
    assert all("near_schedule_id" in g for g in gaps)


def test_gaps_requires_membership(client):
    _signup_and_login(client, "gapowner@test.com")
    trip_id = client.post(
        "/api/trips",
        json={"title": "여행", "start_date": "2026-09-01", "end_date": "2026-09-02", "region": "서울"},
    ).get_json()["data"]["trip_id"]
    client.post("/api/auth/logout")
    _signup_and_login(client, "gapstranger@test.com")
    assert client.get(f"/api/trips/{trip_id}/gaps").status_code == 404


# ---- healthz / 정적 페이지 ----


def test_healthz_reports_db_ok(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok" and data["db"] == "ok"


def test_terms_and_privacy_pages_render(client):
    assert client.get("/terms").status_code == 200
    assert client.get("/privacy").status_code == 200
    assert client.get("/forgot-password").status_code == 200
    assert client.get("/reset-password?token=abc").status_code == 200


# ---- 회원 탈퇴 보호 (UI-10) ----


def test_delete_account_blocked_when_owning_shared_trip(client):
    _signup_and_login(client, "delowner@test.com")
    trip_id = client.post(
        "/api/trips",
        json={"title": "공유중 여행", "start_date": "2026-09-01", "end_date": "2026-09-02", "region": "서울"},
    ).get_json()["data"]["trip_id"]
    client.post("/api/auth/logout")

    _signup_and_login(client, "delmember@test.com")
    client.post("/api/auth/logout")

    _signup_and_login(client, "delowner@test.com")
    client.post(f"/api/trips/{trip_id}/members", json={"email": "delmember@test.com", "role": "VIEWER"})

    resp = client.delete("/api/users/me")
    assert resp.status_code == 409
    assert "소유권" in resp.get_json()["error"]["message"]

    # 멤버 없는 상태로 만들면(여행 삭제) 탈퇴 가능 + 소유 여행 함께 정리
    client.delete(f"/api/trips/{trip_id}")
    resp = client.delete("/api/users/me")
    assert resp.status_code == 200


def test_delete_account_soft_deletes_solo_trips(client):
    _signup_and_login(client, "delsolo@test.com")
    client.post(
        "/api/trips",
        json={"title": "혼자 여행", "start_date": "2026-09-01", "end_date": "2026-09-02", "region": "서울"},
    )
    resp = client.delete("/api/users/me")
    assert resp.status_code == 200

    # 탈퇴한 계정으로 로그인 불가
    resp = client.post("/api/auth/login", json={"email": "delsolo@test.com", "password": "abcd1234"})
    assert resp.status_code == 401
