"""AI Recommendation Engine — 취향 기반 추천 (설계서 9.2절).

Flask/DB에 의존하지 않는 순수 Python 모듈이다. Gemini API 키가 없는 환경이거나
호출이 실패했을 때는 여기 정의된 "규칙 기반 폴백"(카테고리 매칭 + 거리 + 관심사
가중치, 8.3절)을 스코어링 경로로 사용한다(연동 여부는 app/services/recommend_service.py
의 _score가 판단). 후보는 이미 검증된 PLACE 레코드에서만 고르므로 환각(존재하지 않는
장소 추천) 문제가 구조적으로 발생하지 않는다.
"""

from __future__ import annotations

from dataclasses import dataclass

from .route_engine import ROAD_FACTOR, SPEED_KMH, haversine_km

ALLERGY_KEYWORDS = {
    "갑각류": ["새우", "게", "랍스터", "가재"],
    "해산물": ["회", "조개", "굴", "해산물", "생선"],
    "땅콩": ["땅콩"],
    "유제품": ["치즈", "크림", "우유", "버터"],
    "밀가루": ["빵", "면", "파스타", "피자", "국수"],
}

# PLACE.category → PROFILE.interests 가중치 키 매핑 (1.6절 관심사 정의)
CATEGORY_INTEREST_KEY = {
    "CAFE": "cafe",
    "ATTRACTION": "photo",
    "SHOPPING": "shopping",
}
DEFAULT_INTEREST_WEIGHT = 0.5


@dataclass
class CandidateInput:
    place_id: int
    name: str
    category: str
    lat: float
    lng: float
    price_level: int | None = None


@dataclass
class ProfileInput:
    allergy: list[str]
    budget_level: int | None
    interests: dict[str, float]


@dataclass
class ScoredCandidate:
    place_id: int
    score: float  # 0~100
    reason: str


def hard_filter(candidates, profile, excluded_place_ids):
    """알레르기·예산·중복 제외 (9.2.1절 ② 하드 필터, TC-201/202)."""
    allergy_words = {
        word
        for allergy in profile.allergy or []
        for word in ALLERGY_KEYWORDS.get(allergy, [])
    }

    result = []
    for c in candidates:
        if c.place_id in excluded_place_ids:
            continue
        if allergy_words and c.category in ("RESTAURANT", "CAFE") and any(w in c.name for w in allergy_words):
            continue
        if profile.budget_level is not None and c.price_level is not None and c.price_level > profile.budget_level:
            continue
        result.append(c)
    return result


def _rule_based_score(candidate, profile):
    """카테고리 일치(40) + 관심사 가중치(0~30) — 거리는 9.2.3절 detour 페널티에서 별도 반영."""
    interest_key = CATEGORY_INTEREST_KEY.get(candidate.category)
    weight = profile.interests.get(interest_key, DEFAULT_INTEREST_WEIGHT) if interest_key else DEFAULT_INTEREST_WEIGHT
    return 40 + 60 * weight


def score_candidates(candidates, profile, anchor, transport, count=5):
    """9.2.3절 스코어링 보정: final = 0.7*base + 0.3*(100 - min(100, detour_minutes*4))."""
    speed = SPEED_KMH[transport]
    scored = []
    for c in candidates:
        distance_km = haversine_km(anchor[0], anchor[1], c.lat, c.lng) * ROAD_FACTOR
        detour_min = distance_km / speed * 60
        base_score = _rule_based_score(c, profile)
        final = 0.7 * base_score + 0.3 * (100 - min(100, detour_min * 4))
        final = round(min(100.0, max(0.0, final)), 1)

        interest_key = CATEGORY_INTEREST_KEY.get(c.category)
        interest_label = {"cafe": "카페", "photo": "사진 명소", "shopping": "쇼핑"}.get(interest_key, "장소")
        reason = f"{interest_label} 선호와 거리 {distance_km:.1f}km 근접도를 반영한 기본 추천입니다."

        scored.append(ScoredCandidate(place_id=c.place_id, score=final, reason=reason))

    scored.sort(key=lambda s: s.score, reverse=True)
    return scored[:count]


def recommend(candidates, profile, excluded_place_ids, anchor, transport, count=5):
    """전체 파이프라인: 하드 필터 → 스코어링 → 상위 N개 (9.2.1절)."""
    filtered = hard_filter(candidates, profile, excluded_place_ids)
    return score_candidates(filtered, profile, anchor, transport, count)
