# enough authoritative (paper / official-docs / github / reputable-press) sources for full validation
# credit. Tuned to a realistic target rather than a perfect ratio.
VALIDATION_TARGET = 6


def quality_score(discovered: int, validated: int, hallucination_risk: float, rounds: int,
                  avg_relevance: float = 0.0, content_fetched: int = 0,
                  coverage_ledger_score: float | None = None,
                  refuted: int = 0, dead_links: int = 0) -> dict:
    if coverage_ledger_score is None:
        coverage_ledger_score = min(discovered / 20, 1.0)
    coverage = coverage_ledger_score * 18
    # Credit the ABSOLUTE number of validated sources toward a target — NOT validated/discovered.
    # The ratio perversely punished thorough discovery: surfacing 50 blogs alongside 6 primary sources
    # scored worse than finding only the 6. What matters for trust is "did we gather enough authoritative
    # sources", so reaching the target earns full marks regardless of how many low-tier blogs were also seen.
    val_ratio = min(validated / VALIDATION_TARGET, 1.0) * 22
    grounding = (1.0 - max(0.0, min(hallucination_risk, 1.0))) * 30
    relevance = max(0.0, min(avg_relevance, 1.0)) * 15
    depth = (min(content_fetched / 12, 1.0) * 0.6 + min(rounds / 3, 1.0) * 0.4) * 15
    breakdown = {
        "coverage": round(coverage), "validation": round(val_ratio),
        "grounding": round(grounding), "relevance": round(relevance), "depth": round(depth),
    }
    # Grounding GATE (P2-3): confirmed defects multiplicatively cap the whole score, so a verbose,
    # well-sourced but partly-WRONG report can't ride volume to a high number. Each refuted claim knocks
    # ~10% off (floored at 0.5); each dead/fabricated citation a softer ~5% (floored at 0.7). Clean reports
    # (refuted==0, dead_links==0) are unaffected — gate == 1.0.
    gate = 1.0
    if refuted > 0:
        gate *= max(0.5, 1.0 - 0.10 * refuted)
    if dead_links > 0:
        gate *= max(0.7, 1.0 - 0.05 * dead_links)
    score = (coverage + val_ratio + grounding + relevance + depth) * gate
    return {"score": min(round(score), 100), "breakdown": breakdown}


# ── Honest hallucination aggregate (P0-1) ─────────────────────────────────────────────────────────
# entail_report's risk is a CALIBRATED component (it keeps NEI < refuted on purpose, locked by tests).
# This is the HEADLINE number the product reports and gates "<10%" on. It is deliberately stricter and
# more complete: an unsupported claim is unsupported whether merely-unestablished (NEI) or actively
# contradicted (refuted), so NEI counts near-full; and the real defects the entailment judge cannot price
# — cross-source CONFLICTS, dead/fabricated citation LINKS, claims the verifier had to CORRECT/drop, and
# UNCITED factual sentences — each raise risk. This module never caps/floors to flatter a target; the
# min(.,1.0) only bounds a fraction into [0,1].
NEI_WEIGHT_HONEST = 0.8   # NEI = unsupported; near-full, but an active contradiction (refuted=1.0) is worse
W_CONFLICT = 0.5          # a cross-source disagreement on a cited claim
W_DEAD = 0.5              # a cited URL that is dead/fabricated (the citation cannot be verified at all)
W_CORRECTION = 0.5        # a claim the 2nd-model verifier had to rewrite/drop (a real defect the model produced)
W_UNCITED = 1.0           # a factual sentence with NO valid citation — unsupported by construction


DEGRADED_FLOOR = 0.10     # when the entailment judge did NOT run (cosine-only), risk cannot be below this:
                          # cosine is symmetric and can't see contradiction, so a confident "<10%" is unearned


def aggregate_risk(refuted: int, nei: int, total_claims: int, *, conflicts: int = 0,
                   dead_citations: int = 0, corrections: int = 0, uncited: int = 0,
                   degraded: bool = False, degraded_floor: float = DEGRADED_FLOOR,
                   nei_weight: float = NEI_WEIGHT_HONEST, w_conflict: float = W_CONFLICT,
                   w_dead: float = W_DEAD, w_correction: float = W_CORRECTION,
                   w_uncited: float = W_UNCITED) -> dict:
    """Honest, uncapped hallucination-risk aggregate. ``corrections`` and ``uncited`` were real claims, so
    they expand the claim base (they can't be free); ``conflicts``/``dead_citations`` are penalties on the
    existing cited-claim base. When ``degraded`` (the entailment judge did not actually run, so cosine is
    the sole signal) a floor is applied so an over-confident cosine zero cannot be reported as a low risk —
    this RAISES risk to reflect genuine uncertainty, never lowers it (honesty, not a target-flattering cap).
    Returns ``{"risk", "base", "components", "degraded"}``."""
    base = max(int(total_claims) + int(corrections) + int(uncited), 1)
    numer = (refuted + nei_weight * nei + w_conflict * conflicts + w_dead * dead_citations
             + w_correction * corrections + w_uncited * uncited)
    risk = min(numer / base, 1.0)
    if degraded:
        risk = max(risk, degraded_floor)     # uncertainty floor — only ever raises the number
    risk = round(risk, 3)
    return {"risk": risk, "base": base, "degraded": bool(degraded),
            "components": {"refuted": int(refuted), "nei": int(nei), "conflicts": int(conflicts),
                           "dead_citations": int(dead_citations), "corrections": int(corrections),
                           "uncited": int(uncited)}}
