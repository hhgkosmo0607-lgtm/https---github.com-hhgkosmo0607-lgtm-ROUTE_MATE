from app.engines import planb_engine as pb


def _candidate(pid, lat, lng, category="CAFE"):
    return pb.PlanBCandidateInput(place_id=pid, name=f"place{pid}", category=category, lat=lat, lng=lng)


def test_eligible_categories_restricts_to_indoor_for_rain():
    assert pb.eligible_categories("ATTRACTION", "RAIN") == pb.INDOOR_CATEGORIES


def test_eligible_categories_matches_original_for_other_triggers():
    assert pb.eligible_categories("RESTAURANT", "WAIT") == {"RESTAURANT"}
    assert pb.eligible_categories("RESTAURANT", "MANUAL") == {"RESTAURANT"}


def test_score_candidate_prefers_closer_place():
    anchor = (37.5665, 126.9780)
    near = _candidate(1, 37.5666, 126.9781)
    far = _candidate(2, 37.65, 127.05)

    assert pb.score_candidate(near, anchor, 0.5) > pb.score_candidate(far, anchor, 0.5)


def test_rank_candidates_returns_top_n_sorted():
    anchor = (37.5665, 126.9780)
    candidates = [_candidate(i, 37.5665 + i * 0.01, 126.9780) for i in range(5)]

    ranked = pb.rank_candidates(candidates, anchor, 0.7, count=3)

    assert len(ranked) == 3
    scores = [score for _, score in ranked]
    assert scores == sorted(scores, reverse=True)
