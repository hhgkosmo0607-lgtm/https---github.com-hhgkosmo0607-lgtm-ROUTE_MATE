from app.engines import recommender as rec


def _candidate(pid, name, category, lat=37.55, lng=126.98, price=2):
    return rec.CandidateInput(place_id=pid, name=name, category=category, lat=lat, lng=lng, price_level=price)


def _profile(allergy=None, budget_level=3, interests=None):
    return rec.ProfileInput(allergy=allergy or [], budget_level=budget_level, interests=interests or {})


def test_hard_filter_excludes_allergy_risk():
    # TC-201: 갑각류 알레르기 + 해산물집 후보 → 위험 업종 후보 제외
    candidates = [
        _candidate(1, "동해 새우 전문점", "RESTAURANT"),
        _candidate(2, "정갈한 한식당", "RESTAURANT"),
    ]
    profile = _profile(allergy=["갑각류"])

    result = rec.hard_filter(candidates, profile, excluded_place_ids=set())

    assert {c.place_id for c in result} == {2}


def test_hard_filter_excludes_already_scheduled():
    # TC-202: 일정에 이미 있는 장소는 후보에서 제외
    candidates = [_candidate(1, "남산타워", "ATTRACTION"), _candidate(2, "경복궁", "ATTRACTION")]
    profile = _profile()

    result = rec.hard_filter(candidates, profile, excluded_place_ids={1})

    assert {c.place_id for c in result} == {2}


def test_hard_filter_excludes_over_budget():
    candidates = [_candidate(1, "고급 오마카세", "RESTAURANT", price=5)]
    profile = _profile(budget_level=2)

    result = rec.hard_filter(candidates, profile, excluded_place_ids=set())

    assert result == []


def test_score_candidates_penalizes_detour_distance():
    # TC-205: 우회시간이 큰 후보일수록 final 점수가 낮아야 한다.
    near = _candidate(1, "가까운 카페", "CAFE", lat=37.5665, lng=126.9780)
    far = _candidate(2, "먼 카페", "CAFE", lat=37.7, lng=127.2)
    profile = _profile(interests={"cafe": 0.8})
    anchor = (37.5665, 126.9780)

    scored = rec.score_candidates([near, far], profile, anchor, "CAR", count=5)
    scores_by_id = {s.place_id: s.score for s in scored}

    assert scores_by_id[1] > scores_by_id[2]


def test_score_candidates_returns_top_n_sorted_desc():
    candidates = [_candidate(i, f"카페{i}", "CAFE", lat=37.5665 + i * 0.001, lng=126.9780) for i in range(10)]
    profile = _profile(interests={"cafe": 0.9})
    anchor = (37.5665, 126.9780)

    scored = rec.score_candidates(candidates, profile, anchor, "WALK", count=3)

    assert len(scored) == 3
    assert scored[0].score >= scored[1].score >= scored[2].score


def test_recommend_pipeline_end_to_end():
    candidates = [
        _candidate(1, "새우 맛집", "RESTAURANT"),
        _candidate(2, "이미 일정에 있음", "RESTAURANT"),
        _candidate(3, "좋은 한식당", "RESTAURANT"),
    ]
    profile = _profile(allergy=["갑각류"])
    anchor = (37.55, 126.98)

    result = rec.recommend(candidates, profile, excluded_place_ids={2}, anchor=anchor, transport="TRANSIT")

    assert [c.place_id for c in result] == [3]
    assert 0 <= result[0].score <= 100
