from flask import current_app

from ..adapters.osm_adapter import OSMAdapter

_CATEGORY_BY_OSM = {
    "amenity": {"restaurant": "RESTAURANT", "fast_food": "RESTAURANT", "food_court": "RESTAURANT", "cafe": "CAFE"},
    "tourism": None,  # None → 카테고리 자체가 ATTRACTION
    "leisure": None,
    "shop": None,
}
_CATEGORY_DEFAULTS = {"tourism": "ATTRACTION", "leisure": "ATTRACTION", "shop": "SHOPPING"}


def _guess_category(osm_category, osm_type):
    sub = _CATEGORY_BY_OSM.get(osm_category)
    if isinstance(sub, dict):
        return sub.get(osm_type, _CATEGORY_DEFAULTS.get(osm_category, "ETC"))
    if osm_category in _CATEGORY_DEFAULTS:
        return _CATEGORY_DEFAULTS[osm_category]
    return "ETC"


def _place_payload(dto, *, with_address=True):
    """PlaceDTO를 API 응답 dict로 변환. bbox POI(Overpass)는 주소가 없어 with_address=False."""
    return {
        "name": dto.name,
        "category": _guess_category(dto.osm_category, dto.osm_type),
        "lat": dto.lat,
        "lng": dto.lng,
        "address": dto.address if with_address else None,
    }


MAX_BBOX_DEG = 0.03  # 약 3km — 이보다 넓으면 "확대 필요"로 응답 (Overpass 부하·마커 과밀 방지)
MAX_BBOX_DEG_FILTERED = 0.12  # 키워드/카테고리 검색은 결과가 걸러지므로 약 13km까지 허용

# 네이버식 카테고리 검색어 → OSM 태그 필터
CATEGORY_KEYWORDS = {
    "카페": ("amenity", "cafe"),
    "커피": ("amenity", "cafe"),
    "음식점": ("amenity", "restaurant|fast_food|food_court"),
    "맛집": ("amenity", "restaurant|fast_food|food_court"),
    "식당": ("amenity", "restaurant|fast_food|food_court"),
    "레스토랑": ("amenity", "restaurant"),
    "패스트푸드": ("amenity", "fast_food"),
    "관광지": ("tourism", "attraction|museum|gallery|viewpoint|zoo|theme_park"),
    "명소": ("tourism", "attraction|museum|gallery|viewpoint|zoo|theme_park"),
    "가볼만한곳": ("tourism", "attraction|museum|gallery|viewpoint|zoo|theme_park"),
    "가볼만한 곳": ("tourism", "attraction|museum|gallery|viewpoint|zoo|theme_park"),
    "박물관": ("tourism", "museum"),
    "미술관": ("tourism", "gallery"),
    "쇼핑": ("shop", "department_store|mall|supermarket|gift"),
    "백화점": ("shop", "department_store"),
    "편의점": ("shop", "convenience"),
}


def nearby_places(south, west, north, east, query=None):
    """지도 화면(bbox) 안의 POI 목록 (FR-502). 반환: (places, need_zoom).

    query가 카테고리 검색어(카페, 맛집 등)면 태그 필터로, 그 외(상호명·장소명)는
    두 결과를 합친다: ① 전역 지오코딩(Nominatim) — 지도 화면 밖에 있어도 찾아내고
    관련도 순으로 정렬되므로 "경복궁" 같은 정확한 이름이 맨 위에 온다, ② 현재 화면
    bbox 안의 부분일치 POI(Overpass) — 네이버 지도의 "이 지역에서 검색"처럼 화면에
    보이는 유사 후보도 함께 보여준다. ①을 먼저, ②를 이어붙이고 이름 중복은 제거한다.
    """
    if not current_app.config.get("MAP_ADAPTER_ENABLED"):
        return [], False

    query = (query or "").strip()
    keyword, tag_filter = None, None
    if query:
        tag_filter = CATEGORY_KEYWORDS.get(query.replace(" ", "")) or CATEGORY_KEYWORDS.get(query)
        if tag_filter is None:
            keyword = query

    adapter = OSMAdapter(contact_email=current_app.config.get("MAP_CONTACT_EMAIL"))

    global_results = []
    if keyword:
        try:
            global_results = [_place_payload(r) for r in adapter.geocode(keyword, limit=5)]
        except Exception:
            current_app.logger.warning("global place search failed", exc_info=True)

    max_bbox = MAX_BBOX_DEG_FILTERED if query else MAX_BBOX_DEG
    if (north - south) > max_bbox or (east - west) > max_bbox:
        # 지도가 너무 넓게 확대돼 있어 화면 POI 조회는 건너뛴다. 전역 검색 결과가
        # 있으면 그것만으로도 응답하고, 없을 때만 "확대해주세요" 안내가 필요하다.
        return global_results, not global_results

    try:
        nearby = adapter.nearby_pois(south, west, north, east, keyword=keyword, tag_filter=tag_filter)
    except Exception:
        current_app.logger.warning("nearby POI fetch failed", exc_info=True)
        nearby = []

    seen_names = {g["name"] for g in global_results}
    nearby_payload = [
        _place_payload(r, with_address=False) for r in nearby if r.name not in seen_names
    ]
    return global_results + nearby_payload, False


def search_places(query, region=None):
    """장소 통합 검색 (FR-202). Nominatim이 비활성/실패 시 빈 목록을 반환한다(8.3절 폴백).

    region은 검색어에 이어붙이지 않는다. 예전에는 "{query} {region}"으로 질의했는데,
    여행 지역이 부산인데 "경복궁"을 검색하면 Nominatim이 "경복궁 부산"을 통째로 찾아
    결과가 0건이 되어 정작 찾으려던 장소가 안 나오는 문제가 있었다. 사용자는 여행 지역
    밖의 장소도 검색할 수 있어야 하므로(FR-202), 검색어 그대로 전역 질의해 관련도 순으로
    받는다 — "경복궁"이면 실제 경복궁이 맨 위에 온다.
    """
    if not query:
        return []
    if not current_app.config.get("MAP_ADAPTER_ENABLED"):
        return []

    adapter = OSMAdapter(contact_email=current_app.config.get("MAP_CONTACT_EMAIL"))
    try:
        results = adapter.geocode(query)
    except Exception:
        current_app.logger.warning("place search failed, returning empty results", exc_info=True)
        return []

    return [_place_payload(r) for r in results]
