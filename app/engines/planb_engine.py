"""Plan B Engine — 상황 대응 일정 재구성 (설계서 9.3절).

Flask/DB에 의존하지 않는 순수 Python 모듈이다. 날씨·영업정보 API가 없는 현재는
PB-RAIN/PB-CLOSED 자동 감지는 지원하지 않고, PB-WAIT/PB-MANUAL(사용자 수동 발동)만
지원한다. RAIN을 트리거로 사용자가 직접 등록하는 경우에는 9.3.2절의 실내 카테고리
제한 규칙을 그대로 적용한다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .route_engine import ROAD_FACTOR, haversine_km

INDOOR_CATEGORIES = {"CAFE", "SHOPPING"}


@dataclass
class PlanBCandidateInput:
    place_id: int
    name: str
    category: str
    lat: float
    lng: float
    price_level: int | None = None


def eligible_categories(original_category, trigger_type):
    """우천(RAIN) 조건은 실내 카테고리로 제한하고, 그 외는 원래 카테고리와 동일하게 맞춘다."""
    if trigger_type == "RAIN":
        return INDOOR_CATEGORIES
    return {original_category}


def score_candidate(candidate, anchor, profile_interest_weight):
    """카테고리 일치(40) + 근접도(30) + 프로필 적합도(30) (9.3.2절)."""
    distance_km = haversine_km(anchor[0], anchor[1], candidate.lat, candidate.lng) * ROAD_FACTOR
    proximity = max(0.0, 30 - distance_km * 15)  # 2km 근방에서 0으로 수렴
    fit = 30 * profile_interest_weight
    return round(40 + proximity + fit, 1)


def rank_candidates(candidates, anchor, profile_interest_weight, count=3):
    scored = [(c, score_candidate(c, anchor, profile_interest_weight)) for c in candidates]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:count]
