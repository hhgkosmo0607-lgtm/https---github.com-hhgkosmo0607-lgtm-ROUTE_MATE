"""Google Gemini API 어댑터 — 추천 스코어링·사유 생성 (설계서 9.2.1절 ③, FR-301~304).

무료 티어(Google AI Studio) 기준. 후보 풀은 이미 하드필터를 통과한 PLACE 레코드만
넘기고, 프롬프트에 "목록에 없는 장소는 만들어내지 마라"는 제약을 명시한 뒤 응답의
place_id가 후보 집합에 실제로 있는지 상위 계층(recommend_service)에서 다시 검증한다
— 존재하지 않는 장소를 추천하는 환각(hallucination) 문제를 구조적으로 차단한다.

실패(타임아웃·키 미설정·쿼터 초과·파싱 실패) 시 예외를 던지며, 상위 계층이
8.3절 규칙 기반 폴백으로 전환한다.
"""

import json
import logging

import requests

logger = logging.getLogger(__name__)

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-flash-latest"

RESPONSE_SCHEMA = {
    "type": "ARRAY",
    "items": {
        "type": "OBJECT",
        "properties": {
            "place_id": {"type": "INTEGER"},
            "score": {"type": "NUMBER"},
            "reason": {"type": "STRING"},
        },
        "required": ["place_id", "score", "reason"],
    },
}

INTEREST_LABELS = {"cafe": "카페", "photo": "사진 명소", "shopping": "쇼핑"}


class GeminiAdapter:
    def __init__(self, api_key, model=DEFAULT_MODEL, timeout=20):
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def score_candidates(self, candidates, profile, anchor, transport, count=5):
        """스코어링 요청 → [{place_id, score, reason}, ...] (후보 집합 검증은 호출자 책임)."""
        if not candidates:
            return []

        prompt = self._build_prompt(candidates, profile, anchor, transport, count)
        resp = requests.post(
            GEMINI_URL.format(model=self.model),
            params={"key": self.api_key},
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "responseSchema": RESPONSE_SCHEMA,
                    "temperature": 0.4,
                },
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        items = json.loads(text)
        if not isinstance(items, list):
            raise ValueError("Gemini response is not a list")
        return items

    def _build_prompt(self, candidates, profile, anchor, transport, count):
        interests = profile.interests or {}
        interest_lines = ", ".join(
            f"{INTEREST_LABELS.get(k, k)}={v}" for k, v in interests.items()
        ) or "없음"
        candidate_lines = "\n".join(
            f"- place_id={c.place_id}, name={c.name}, category={c.category}, "
            f"lat={c.lat}, lng={c.lng}, price_level={c.price_level}"
            for c in candidates
        )
        return (
            "너는 여행 일정 추천 도우미다. 아래 '후보 목록'에 있는 장소 중에서만 골라 "
            f"적합도 순으로 상위 {count}개를 선정해라. 각 항목마다 적합도 점수(score)와 "
            "한국어로 자연스러운 한 문장짜리 추천 이유(reason)를 작성해라. "
            "score는 반드시 0부터 100 사이의 정수다(별점 5점 척도가 아니다). "
            "가장 잘 맞는 곳이 100에 가깝고, 예: 매우 적합 92, 보통 70, 낮음 45. "
            "후보 목록에 없는 place_id를 만들어내면 안 된다.\n\n"
            f"사용자 관심사 가중치: {interest_lines}\n"
            f"이동 수단: {transport}\n"
            f"기준 위치: lat={anchor[0]}, lng={anchor[1]}\n\n"
            f"후보 목록:\n{candidate_lines}\n"
        )
