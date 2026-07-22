import json

import pytest

from app.adapters import gemini_adapter as ga
from app.engines import recommender as rec


def _candidate(pid=1, name="카페", category="CAFE"):
    return rec.CandidateInput(place_id=pid, name=name, category=category, lat=37.5, lng=127.0, price_level=2)


def _profile():
    return rec.ProfileInput(allergy=[], budget_level=None, interests={"cafe": 0.8})


class _FakeResponse:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise ga.requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._payload


def _gemini_payload(items):
    return {"candidates": [{"content": {"parts": [{"text": json.dumps(items)}]}}]}


def test_score_candidates_skips_request_when_no_candidates(monkeypatch):
    calls = []
    monkeypatch.setattr(ga.requests, "post", lambda *a, **k: calls.append((a, k)))

    adapter = ga.GeminiAdapter(api_key="fake-key")
    result = adapter.score_candidates([], _profile(), (37.5, 127.0), "WALK")

    assert result == []
    assert calls == []


def test_score_candidates_parses_valid_response(monkeypatch):
    items = [{"place_id": 1, "score": 88, "reason": "카페 선호와 가까운 거리"}]

    def fake_post(url, params=None, json=None, timeout=None):
        assert params == {"key": "fake-key"}
        assert "gemini-flash-latest" in url
        return _FakeResponse(_gemini_payload(items))

    monkeypatch.setattr(ga.requests, "post", fake_post)

    adapter = ga.GeminiAdapter(api_key="fake-key")
    result = adapter.score_candidates([_candidate()], _profile(), (37.5, 127.0), "WALK", count=3)

    assert result == items


def test_score_candidates_raises_on_non_list_response(monkeypatch):
    monkeypatch.setattr(
        ga.requests, "post", lambda *a, **k: _FakeResponse(_gemini_payload({"not": "a list"}))
    )

    adapter = ga.GeminiAdapter(api_key="fake-key")
    with pytest.raises(ValueError):
        adapter.score_candidates([_candidate()], _profile(), (37.5, 127.0), "WALK")


def test_score_candidates_raises_on_http_error(monkeypatch):
    monkeypatch.setattr(ga.requests, "post", lambda *a, **k: _FakeResponse({}, status_code=429))

    adapter = ga.GeminiAdapter(api_key="fake-key")
    with pytest.raises(ga.requests.HTTPError):
        adapter.score_candidates([_candidate()], _profile(), (37.5, 127.0), "WALK")
