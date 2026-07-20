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

    query가 카테고리 검색어(카페, 맛집 등)면 태그 필터로, 그 외에는 상호명
    부분일치로 검색한다 — 네이버 지도의 "이 지역에서 검색"과 같은 동작.
    """
    if not current_app.config.get("MAP_ADAPTER_ENABLED"):
        return [], False

    query = (query or "").strip()
    keyword, tag_filter = None, None
    if query:
        tag_filter = CATEGORY_KEYWORDS.get(query.replace(" ", "")) or CATEGORY_KEYWORDS.get(query)
        if tag_filter is None:
            keyword = query

    max_bbox = MAX_BBOX_DEG_FILTERED if query else MAX_BBOX_DEG
    if (north - south) > max_bbox or (east - west) > max_bbox:
        return [], True

    adapter = OSMAdapter(contact_email=current_app.config.get("MAP_CONTACT_EMAIL"))
    try:
        results = adapter.nearby_pois(south, west, north, east, keyword=keyword, tag_filter=tag_filter)
    except Exception:
        current_app.logger.warning("nearby POI fetch failed", exc_info=True)
        return [], False

    return [
        {
            "name": r.name,
            "category": _guess_category(r.osm_category, r.osm_type),
            "lat": r.lat,
            "lng": r.lng,
            "address": None,
        }
        for r in results
    ], False


def search_places(query, region=None):
    """장소 통합 검색 (FR-202). Nominatim이 비활성/실패 시 빈 목록을 반환한다(8.3절 폴백)."""
    if not query:
        return []
    if not current_app.config.get("MAP_ADAPTER_ENABLED"):
        return []

    adapter = OSMAdapter(contact_email=current_app.config.get("MAP_CONTACT_EMAIL"))
    q = f"{query} {region}" if region else query
    try:
        results = adapter.geocode(q)
    except Exception:
        current_app.logger.warning("place search failed, returning empty results", exc_info=True)
        return []

    return [
        {
            "name": r.name,
            "category": _guess_category(r.osm_category, r.osm_type),
            "address": r.address,
            "lat": r.lat,
            "lng": r.lng,
        }
        for r in results
    ]
