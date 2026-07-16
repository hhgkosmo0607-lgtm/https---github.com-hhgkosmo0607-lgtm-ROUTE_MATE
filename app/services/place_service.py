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
