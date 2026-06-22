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

def test_uses_coverage_ledger_score():
    s = quality_score(10, 5, 0.2, 2, 0.5, 6, coverage_ledger_score=0.8)
    assert s["breakdown"]["coverage"] == round(0.8 * 18)

def test_grounding_gate_penalizes_refuted_and_dead_links():
    base = quality_score(20, 12, 0.1, 3, 0.7, 12)["score"]
    assert quality_score(20, 12, 0.1, 3, 0.7, 12, refuted=3)["score"] < base       # contradictions cap it
    assert quality_score(20, 12, 0.1, 3, 0.7, 12, dead_links=4)["score"] < base     # dead citations cap it

def test_grounding_gate_is_noop_when_clean():
    # a clean report (no refuted claims, no dead links) is unaffected -> back-compatible default
    assert (quality_score(20, 12, 0.1, 3, 0.7, 12)["score"]
            == quality_score(20, 12, 0.1, 3, 0.7, 12, refuted=0, dead_links=0)["score"])
