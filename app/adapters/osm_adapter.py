"""OpenStreetMap 공개 데모 서버 기반 어댑터 (Nominatim 지오코딩 + OSRM 경로).

무료·키 불필요 — 테스트/수업용으로 적합하다. 두 서비스 모두 "초당 1회 이하,
합리적 비상업 사용" 정책이 있어 프로세스 내 최소 요청 간격을 강제한다.
실패 시 예외를 던지며, 상위 계층(route_engine)이 Haversine 폴백으로 전환한다(8.3절).

주의: 요청 간격 제한은 프로세스 단일 인스턴스 기준이다. 다중 워커로 배포하면
전체 합산 요청 빈도가 정책을 넘을 수 있으므로, 운영 규모가 커지면 자체 OSRM/
Nominatim 인스턴스로 이전해야 한다.
"""

import logging
import re
import time

import requests

from ..utils.ttl_cache import TTLCache
from .dto import PlaceDTO

# 12.2절 캐시 전략: 장소검색 24h, POI 1h, 거리행렬(장소 쌍) 7일
_cache = TTLCache(maxsize=500)
GEOCODE_TTL = 24 * 3600
POI_TTL = 3600
MATRIX_TTL = 7 * 24 * 3600

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
OSRM_URL = "https://router.project-osrm.org/table/v1/{profile}/{coords}"
# 공개 Overpass 서버는 개별 인스턴스가 수시로 504/슬롯초과를 내므로 미러를 순차 시도한다
OVERPASS_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]

PROFILE_MAP = {"WALK": "foot", "CAR": "driving", "TRANSIT": "driving"}

# 지도 화면(bbox) 안에서 조회할 기본 POI 태그 클래스 (FR-502 상세보기 대상)
POI_TAG_CLASSES = [
    ("amenity", "restaurant|cafe|fast_food"),
    ("tourism", "attraction|museum|gallery|viewpoint|zoo|theme_park"),
    ("shop", "department_store|mall|gift"),
]
# 이름 키워드 검색 시에는 태그 종류를 넓게 잡는다 (상호명 매칭이 1차 필터라서)
KEYWORD_TAG_KEYS = ("amenity", "tourism", "shop", "leisure")

_MIN_INTERVAL = 1.05  # 데모 서버 정책(초당 1회) + 여유 마진
_last_request_at = {"osrm": 0.0, "nominatim": 0.0, "overpass": 0.0}

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
        cache_key = ("geocode", query.strip(), country_codes, limit)
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        _throttle("nominatim")
        resp = requests.get(
            NOMINATIM_URL,
            params={"q": query, "format": "jsonv2", "limit": limit, "countrycodes": country_codes},
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        results = [
            PlaceDTO(
                name=r.get("name") or r["display_name"].split(",")[0],
                lat=float(r["lat"]),
                lng=float(r["lon"]),
                address=r.get("display_name"),
                ext_id=str(r.get("osm_id")) if r.get("osm_id") is not None else None,
                osm_category=r.get("category"),
                osm_type=r.get("type"),
            )
            for r in resp.json()
        ]
        _cache.set(cache_key, results, GEOCODE_TTL)
        return results

    def _overpass_request(self, query, url):
        resp = requests.post(
            url,
            data={"data": query},
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout + 10,
        )
        resp.raise_for_status()
        return resp.json()  # 슬롯 초과 시 HTML이 오므로 JSON 파싱 실패 = 재시도 대상

    def nearby_pois(self, south, west, north, east, limit=80, keyword=None, tag_filter=None):
        """bbox 안의 POI 조회 (Overpass API, FR-502).

        keyword: 상호명 부분일치(정규식 이스케이프 처리). tag_filter: (태그키, 값정규식)
        — 예: ("amenity", "cafe")로 카테고리 검색. 둘 다 없으면 기본 클래스 전체.
        공개 서버는 동시 슬롯 제한(2)이 있어 간헐적으로 비-JSON 응답을 준다 —
        짧게 대기 후 1회 재시도한다.
        """
        bbox = f"{south},{west},{north},{east}"
        if keyword:
            safe = re.escape(keyword.replace('"', ""))
            lines = [f'node["{key}"]["name"~"{safe}"]({bbox});' for key in KEYWORD_TAG_KEYS]
        elif tag_filter:
            key, value_re = tag_filter
            lines = [f'node["{key}"~"{value_re}"]["name"]({bbox});']
        else:
            lines = [f'node["{key}"~"{value_re}"]["name"]({bbox});' for key, value_re in POI_TAG_CLASSES]

        query = "[out:json][timeout:10];\n(\n  " + "\n  ".join(lines) + f"\n);\nout {limit};"

        # 같은 화면 재조회·팬 반복을 흡수 (bbox 4자리 반올림 ≈ 10m 단위)
        cache_key = ("poi", round(south, 4), round(west, 4), round(north, 4), round(east, 4), keyword, tag_filter, limit)
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

        data = None
        last_exc = None
        for i, url in enumerate(OVERPASS_ENDPOINTS):
            _throttle("overpass")
            try:
                data = self._overpass_request(query, url)
                break
            except (ValueError, requests.RequestException) as exc:
                logger.warning("overpass endpoint failed (%s): %s", url, exc)
                last_exc = exc
                if i == 0:
                    time.sleep(2)  # 슬롯 반환 여유 후 미러 시도
        if data is None:
            raise last_exc

        results = []
        for el in data.get("elements", []):
            tags = el.get("tags", {})
            name = tags.get("name")
            if not name or el.get("lat") is None:
                continue
            category = tags.get("amenity") or tags.get("tourism") or tags.get("shop")
            osm_cat = "amenity" if "amenity" in tags else ("tourism" if "tourism" in tags else "shop")
            results.append(
                PlaceDTO(
                    name=name,
                    lat=el["lat"],
                    lng=el["lon"],
                    ext_id=str(el.get("id")),
                    osm_category=osm_cat,
                    osm_type=category,
                )
            )
        _cache.set(cache_key, results, POI_TTL)
        return results

    def distance_matrix(self, coords, mode):
        profile = PROFILE_MAP.get(mode, "driving")
        coord_str = ";".join(f"{lng},{lat}" for lat, lng in coords)

        # 같은 장소 집합의 재최적화·드래그 재계산을 흡수 (좌표 5자리 ≈ 1m 단위)
        cache_key = ("matrix", profile, mode, tuple((round(la, 5), round(ln, 5)) for la, ln in coords))
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached

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

        result = (durations_min, distances_km)
        _cache.set(cache_key, result, MATRIX_TTL)
        return result
