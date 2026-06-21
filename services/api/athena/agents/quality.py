# enough authoritative (paper / official-docs / github / reputable-press) sources for full validation
# credit. Tuned to a realistic target rather than a perfect ratio.
VALIDATION_TARGET = 6


def quality_score(discovered: int, validated: int, hallucination_risk: float, rounds: int,
                  avg_relevance: float = 0.0, content_fetched: int = 0) -> dict:
    coverage = min(discovered / 20, 1.0) * 18
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
    return {"score": min(round(coverage + val_ratio + grounding + relevance + depth), 100),
            "breakdown": breakdown}
