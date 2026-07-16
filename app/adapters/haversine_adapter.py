"""직선거리 × 도로계수 + 수단별 평균속도 근사 폴백 어댑터 (설계서 8.2/8.3절)."""

from ..engines.route_engine import ROAD_FACTOR, SPEED_KMH, haversine_km


class HaversineFallbackAdapter:
    def geocode(self, query):
        return []  # 근사 어댑터는 지오코딩을 지원하지 않는다 (좌표 직접 입력 필요)

    def distance_matrix(self, coords, mode):
        speed = SPEED_KMH[mode]
        n = len(coords)
        distances_km = [[0.0] * n for _ in range(n)]
        durations_min = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                if i == j:
                    continue
                km = haversine_km(coords[i][0], coords[i][1], coords[j][0], coords[j][1]) * ROAD_FACTOR
                distances_km[i][j] = km
                durations_min[i][j] = km / speed * 60
        return durations_min, distances_km
