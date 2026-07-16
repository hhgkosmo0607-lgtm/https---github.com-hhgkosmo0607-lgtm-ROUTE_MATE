"""OpenStreetMap 공개 데모 서버 기반 어댑터 (Nominatim 지오코딩 + OSRM 경로).

무료·키 불필요 — 테스트/수업용으로 적합하다. 두 서비스 모두 "초당 1회 이하,
합리적 비상업 사용" 정책이 있어 프로세스 내 최소 요청 간격을 강제한다.
실패 시 예외를 던지며, 상위 계층(route_engine)이 Haversine 폴백으로 전환한다(8.3절).

주의: 요청 간격 제한은 프로세스 단일 인스턴스 기준이다. 다중 워커로 배포하면
전체 합산 요청 빈도가 정책을 넘을 수 있으므로, 운영 규모가 커지면 자체 OSRM/
Nominatim 인스턴스로 이전해야 한다.
"""

import logging
import time

import requests

from .dto import PlaceDTO

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/table/v1/{profile}/{coords}"

PROFILE_MAP = {"WALK": "foot", "CAR": "driving", "TRANSIT": "driving"}

_MIN_INTERVAL = 1.05  # 데모 서버 정책(초당 1회) + 여유 마진
_last_request_at = {"osrm": 0.0, "nominatim": 0.0}

logger = logging.getLogger(__name__)


def _throttle(key):
    elapsed = time.monotonic() - _last_request_at[key]
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _last_request_at[key] = time.monotonic()


class OSMAdapter:
    def __init__(self, timeout=5, contact_email=None):
        self.timeout = timeout
        contact = f"; {contact_email}" if contact_email else ""
        self.user_agent = f"RouteMate/1.0 (capstone project{contact})"

    def geocode(self, query, country_codes="kr", limit=5):
        _throttle("nominatim")
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "jsonv2", "limit": limit, "countrycodes": country_codes},
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        results = resp.json()
        return [
            PlaceDTO(
                name=r.get("name") or r["display_name"].split(",")[0],
                lat=float(r["lat"]),
                lng=float(r["lon"]),
                address=r.get("display_name"),
                ext_id=str(r.get("osm_id")) if r.get("osm_id") is not None else None,
                osm_category=r.get("category"),
                osm_type=r.get("type"),
            )
            for r in results
        ]

    def distance_matrix(self, coords, mode):
        profile = PROFILE_MAP.get(mode, "driving")
        coord_str = ";".join(f"{lng},{lat}" for lat, lng in coords)

        _throttle("osrm")
        resp = requests.get(
            OSRM_URL.format(profile=profile, coords=coord_str),
            params={"annotations": "duration,distance"},
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != "Ok":
            raise RuntimeError(f"OSRM error: {data.get('code')}")

        distances_km = [[(d or 0) / 1000 for d in row] for row in data["distances"]]
        durations_min = [[(d or 0) / 60 for d in row] for row in data["durations"]]

        if mode == "TRANSIT":
            # OSRM에는 대중교통 프로파일이 없다. 도로망 기준 거리(driving)는 그대로
            # 쓰되, 소요시간은 대중교통 평균 속도로 다시 계산한다.
            from ..engines.route_engine import SPEED_KMH

            speed = SPEED_KMH["TRANSIT"]
            durations_min = [[km / speed * 60 for km in row] for row in distances_km]

        return durations_min, distances_km
