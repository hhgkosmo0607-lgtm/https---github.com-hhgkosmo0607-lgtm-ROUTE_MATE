"""부하 테스트 (설계서 13.1절 / 12.1절 성능 목표).

측정 대상:
- 일반 조회 API p95 500ms 이내 (NFR-05)
- 경로 계산 3초 이내 (NFR-06) — 솔버는 n≤12 기준 1초 시간제한 탐색이므로 1초+큐잉이 기대치

실행 예:
  RATELIMIT_ENABLED=false 로 띄운 서버 대상
  .venv/bin/locust -f loadtest/locustfile.py --headless -u 30 -r 3 -t 60s --host http://127.0.0.1:5058

주의: 레이트리밋(로그인 10/분 등)은 단일 IP 부하 테스트에서 가짜 병목이 되므로
서버를 RATELIMIT_ENABLED=false 로 띄운다. 리미터 자체는 단위 테스트로 검증된다.
"""

import itertools
import random

from locust import HttpUser, between, task

_counter = itertools.count()

PLACES = [
    ("경복궁", "ATTRACTION", 37.5796, 126.9770),
    ("명동", "SHOPPING", 37.5636, 126.9834),
    ("남산타워", "ATTRACTION", 37.5512, 126.9882),
    ("이태원", "ETC", 37.5346, 126.9946),
    ("동대문", "SHOPPING", 37.5714, 127.0095),
    ("홍대", "CAFE", 37.5563, 126.9236),
]


class TravelerUser(HttpUser):
    wait_time = between(0.5, 2)

    def _csrf(self):
        token = self.client.get("/api/csrf-token").json()["data"]["csrf_token"]
        return {"X-CSRF-Token": token}

    def on_start(self):
        uid = next(_counter)
        email = f"load{uid}_{random.randint(0, 10**6)}@load.com"
        self.client.post(
            "/api/auth/signup",
            json={"email": email, "password": "abcd1234", "nickname": f"부하{uid}"},
            headers=self._csrf(),
        )
        self.client.post(
            "/api/auth/login", json={"email": email, "password": "abcd1234"}, headers=self._csrf()
        )
        trip = self.client.post(
            "/api/trips",
            json={"title": f"부하 여행 {uid}", "region": "서울", "start_date": "2026-09-01", "end_date": "2026-09-03"},
            headers=self._csrf(),
        ).json()["data"]
        self.trip_id = trip["trip_id"]
        for name, cat, lat, lng in PLACES:
            self.client.post(
                f"/api/trips/{self.trip_id}/places",
                json={"name": name, "category": cat, "lat": lat, "lng": lng},
                headers=self._csrf(),
                name="/api/trips/[id]/places",
            )

    @task(6)
    def view_trips(self):
        self.client.get("/api/trips")

    @task(6)
    def view_schedules(self):
        self.client.get(f"/api/trips/{self.trip_id}/schedules", name="/api/trips/[id]/schedules")

    @task(3)
    def view_expense_summary(self):
        self.client.get(f"/api/trips/{self.trip_id}/expenses/summary", name="/api/trips/[id]/expenses/summary")

    @task(2)
    def view_plan_page(self):
        self.client.get(f"/trips/{self.trip_id}/plan", name="/trips/[id]/plan")

    @task(1)
    def generate_route(self):
        with self.client.post(
            f"/api/trips/{self.trip_id}/route",
            json={"transport": "CAR"},
            headers=self._csrf(),
            name="/api/trips/[id]/route (솔버)",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200 and resp.elapsed.total_seconds() > 3.0:
                resp.failure(f"NFR-06 위반: {resp.elapsed.total_seconds():.2f}s > 3s")
