from dataclasses import dataclass


@dataclass
class PlaceDTO:
    name: str
    lat: float
    lng: float
    address: str | None = None
    ext_id: str | None = None
    osm_category: str | None = None  # Nominatim category (예: amenity, tourism, shop)
    osm_type: str | None = None  # Nominatim type (예: restaurant, cafe)
