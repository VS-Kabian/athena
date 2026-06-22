"""Honest hallucination aggregate (P0-1): the HEADLINE risk the product reports and gates '<10%' on.

Unlike entail_report's calibrated blend (NEI < refuted, locked by its own tests), this aggregate is
deliberately stricter and more complete — NEI counts near-full, and conflicts / dead citations / verifier
corrections / uncited claims each raise risk. It must never be cappable to flatter a target, yet stay
bounded to [0,1]."""
from athena.agents.quality import aggregate_risk


def test_all_refuted_pins_high():
    r = aggregate_risk(refuted=4, nei=0, total_claims=4)
    assert r["risk"] >= 0.9            # every claim contradicted -> headline risk pinned high


def test_all_supported_and_clean_is_zero():
    r = aggregate_risk(refuted=0, nei=0, total_claims=5)
    assert r["risk"] == 0.0            # nothing wrong -> exactly zero, never floored above it


def test_nei_counts_near_full_but_below_refuted():
    nei_only = aggregate_risk(refuted=0, nei=5, total_claims=5)["risk"]
    refuted_only = aggregate_risk(refuted=5, nei=0, total_claims=5)["risk"]
    assert nei_only >= 0.7            # NEI is unsupported -> near-full weight (not the old 0.4 discount)
    assert refuted_only > nei_only    # an active contradiction is still the worst case


def test_conflict_strictly_raises_risk():
    clean = aggregate_risk(refuted=0, nei=0, total_claims=5)["risk"]
    with_conflict = aggregate_risk(refuted=0, nei=0, total_claims=5, conflicts=1)["risk"]
    assert clean == 0.0 and with_conflict > clean


def test_dead_citation_strictly_raises_risk():
    base = aggregate_risk(refuted=0, nei=0, total_claims=5)["risk"]
    with_dead = aggregate_risk(refuted=0, nei=0, total_claims=5, dead_citations=1)["risk"]
    assert with_dead > base


def test_verifier_correction_strictly_raises_risk():
    base = aggregate_risk(refuted=0, nei=0, total_claims=5)["risk"]
    with_corr = aggregate_risk(refuted=0, nei=0, total_claims=5, corrections=1)["risk"]
    assert with_corr > base           # a claim the verifier had to fix/drop is a hallucination event


def test_uncited_claim_strictly_raises_risk():
    base = aggregate_risk(refuted=0, nei=0, total_claims=5)["risk"]
    with_uncited = aggregate_risk(refuted=0, nei=0, total_claims=5, uncited=1)["risk"]
    assert with_uncited > base


def test_risk_is_bounded_to_unit_interval():
    r = aggregate_risk(refuted=10, nei=10, total_claims=5, conflicts=5, dead_citations=5,
                       corrections=5, uncited=5)
    assert 0.0 <= r["risk"] <= 1.0    # a fraction is bounded — but this is NOT a target-flattering cap


def test_honest_aggregate_is_stricter_than_blended_nei():
    # governing principle: the honest headline must never be SOFTER than entail_report's blend.
    # entail_report scores all-NEI at 0.4 (NEI_WEIGHT); the aggregate must exceed it.
    assert aggregate_risk(refuted=0, nei=2, total_claims=2)["risk"] > 0.4


def test_components_breakdown_returned():
    c = aggregate_risk(refuted=1, nei=2, total_claims=5, conflicts=1, dead_citations=1,
                       corrections=1, uncited=1)["components"]
    assert c == {"refuted": 1, "nei": 2, "conflicts": 1, "dead_citations": 1,
                 "corrections": 1, "uncited": 1}
