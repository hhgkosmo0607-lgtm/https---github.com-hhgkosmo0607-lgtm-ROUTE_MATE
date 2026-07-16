"""외부 지도 API 어댑터 인터페이스 (설계서 8.2절).

공급자 교체가 어댑터 구현체 교체만으로 가능하도록 인터페이스를 고정한다(NFR-09).
"""

from typing import Protocol


class MapAdapter(Protocol):
    def geocode(self, query: str) -> list:
        """키워드로 장소를 검색해 PlaceDTO 목록을 반환한다."""
        ...

    def distance_matrix(self, coords: list[tuple[float, float]], mode: str):
        """좌표 목록(lat, lng) 간 n×n (소요시간(분), 거리(km)) 행렬을 반환한다.

        실패 시 예외를 던진다 — 호출부(route_engine)가 Haversine 폴백으로 전환한다.
        """
        ...
