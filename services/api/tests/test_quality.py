from athena.agents.quality import quality_score

def test_not_trivially_100_without_content():
    s = quality_score(discovered=125, validated=125, hallucination_risk=0.0, rounds=3,
                      avg_relevance=0.6, content_fetched=0)
    assert s["score"] < 100  # honest: no page content fetched -> depth not maxed

def test_validation_matters():
    good = quality_score(20, 12, 0.1, 3, 0.7, 12)
    bad = quality_score(20, 0, 0.1, 3, 0.7, 12)
    assert good["score"] > bad["score"]
    assert 0 <= good["score"] <= 100

def test_breakdown_keys():
    s = quality_score(10, 5, 0.2, 2, 0.5, 6)
    assert set(s["breakdown"]) == {"coverage", "validation", "grounding", "relevance", "depth"}
