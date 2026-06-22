"""RAGAS-style faithfulness + ALCE-style citation precision/recall for the eval harness (P2-7).

PURE & reference-free: every metric is computed from ALREADY-COMPUTED per-claim signals — the
entail_report verdict counts, or the verdict list — so there is NO model or DB call here. The live
harness calls these on a real run's trust ledger; offline unit tests call them on synthetic inputs.

LIVE-ONLY (documented, not unit-tested here): the model actually judging claims (entail_report) and the
strict ALCE per-citation 'necessary' ablation (remove a citation, re-check entailment) require a live
model + sources. The metric functions only consume those signals once produced.
"""

_SUPPORTED = "supported"


def faithfulness(*, supported: int, total: int) -> float:
    """RAGAS faithfulness: fraction of cited claims whose cited evidence SUPPORTS them (reference-free,
    from entailment counts where total = supported + refuted + nei). Returns 1.0 when total == 0
    (vacuously faithful — nothing was claimed), mirroring how entail/factcheck treat the no-claims case."""
    total = int(total)
    if total <= 0:
        return 1.0
    return round(max(0, int(supported)) / total, 4)


def faithfulness_from_verdicts(verdicts: list[dict]) -> float:
    """faithfulness() computed straight from entail_report['verdicts'] (each has 'verdict')."""
    total = len(verdicts)
    sup = sum(1 for v in verdicts if str(v.get("verdict", "")).lower() == _SUPPORTED)
    return faithfulness(supported=sup, total=total)


def citation_precision_recall(verdicts: list[dict]) -> dict:
    """ALCE-style citation quality at the claim level, over per-claim entailment verdicts:
      recall    = cited claims whose citation set ENTAILS the claim (verdict 'supported') / cited claims
      precision = cited claims with >=1 NECESSARY, entailing citation / cited claims
                  (the optional 'necessary' flag is a live-run enrichment; absent -> precision == recall)
    A claim with no in-range citation can carry ``cited=False`` and is excluded. Empty / no cited claims
    -> all 1.0 (vacuous). Returns ``{precision, recall, f1}`` each in [0, 1]."""
    cited = [v for v in verdicts if v.get("cited", True)]
    n = len(cited)
    if n == 0:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}
    supported = [v for v in cited if str(v.get("verdict", "")).lower() == _SUPPORTED]
    recall = len(supported) / n
    necessary = [v for v in supported if v.get("necessary", True)]
    precision = len(necessary) / n
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {"precision": round(precision, 4), "recall": round(recall, 4), "f1": round(f1, 4)}
