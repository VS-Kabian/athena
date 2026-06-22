import asyncio
import json
import os

from ..db import fetch, execute
from ..agents.graph import run_research
from .topics import EVAL_TOPICS
from .race import race_score
from .metrics import faithfulness


def _qb(v):
    if v is None:
        return {}
    return json.loads(v) if isinstance(v, str) else v


async def run_eval(llm: dict, providers: list, batch: str, mode: str = "broadcast", rounds: int = 2,
                   topics: list[str] | None = None) -> list[dict]:
    if not llm.get("api_key"):
        from ..api.keys import get_key
        llm["api_key"] = await get_key(llm["provider"])
    topics = topics or EVAL_TOPICS
    results = []
    for topic in topics:
        rows = await fetch("insert into research_runs(topic,rounds_total,status) values($1,$2,'running') returning id",
                           topic, rounds)
        rid = str(rows[0]["id"])
        await run_research(rid, topic, rounds, llm, providers, mode)
        rep = await fetch("select markdown, quality_breakdown, trust from reports "
                          "where run_id=$1 order by created_at desc limit 1", rid)
        report = rep[0]["markdown"] if rep else ""
        qb = _qb(rep[0]["quality_breakdown"]) if rep else {}
        # RAGAS-style faithfulness + claim-level citation recall from the persisted entailment counts
        # (P2-7, reference-free — no extra model call). `.get` keeps it safe if `trust` is absent.
        trust = _qb(rep[0].get("trust")) if rep else {}
        sup = int(trust.get("supported", 0) or 0)
        total_claims = sup + int(trust.get("refuted", 0) or 0) + int(trust.get("nei", 0) or 0)
        faith = faithfulness(supported=sup, total=total_claims)
        cit_recall = faith   # claim-level recall == supported/total; per-citation precision is live-only
        race = await race_score(report, topic, llm)
        fact_risk = qb.get("hallucination_risk")
        # quality_score lives on research_runs, NOT reports (the reports table has no such column)
        run_row = await fetch("select quality_score from research_runs where id=$1", rid)
        qscore = run_row[0]["quality_score"] if run_row else None
        await execute("insert into eval_runs(batch, topic, run_id, race_overall, fact_risk, quality_score, "
                      "faithfulness, citation_recall) values($1,$2,$3,$4,$5,$6,$7,$8)",
                      batch, topic, rid, race["overall"], fact_risk, qscore, faith, cit_recall)
        results.append({"topic": topic, "race": race["overall"], "fact_risk": fact_risk, "quality": qscore,
                        "faithfulness": faith, "citation_recall": cit_recall})
    return results


async def compare_to_previous(batch: str) -> dict:
    rows = await fetch("select batch, avg(race_overall) race, avg(fact_risk) risk, avg(quality_score) q, "
                       "avg(faithfulness) faith "
                       "from eval_runs where batch is not null group by batch order by max(created_at) desc limit 2")
    if not rows:
        return {}
    latest = dict(rows[0])
    prev = dict(rows[1]) if len(rows) > 1 else None
    return {"latest": latest, "previous": prev}


def regression_gate(cmp: dict, *, faith_drop: float = 0.05, risk_rise: float = 0.05) -> dict:
    """Pure regression gate (offline-testable): FAIL if faithfulness dropped or fact_risk rose vs the
    previous batch beyond tolerance. No previous batch -> pass (nothing to regress against)."""
    latest, prev = cmp.get("latest"), cmp.get("previous")
    if not latest or not prev:
        return {"ok": True, "reasons": []}

    def f(d, k):
        v = d.get(k)
        return float(v) if v is not None else None

    reasons = []
    lf, pf = f(latest, "faith"), f(prev, "faith")
    lr, pr = f(latest, "risk"), f(prev, "risk")
    if lf is not None and pf is not None and lf < pf - faith_drop:
        reasons.append(f"faithfulness dropped {pf:.3f} -> {lf:.3f}")
    if lr is not None and pr is not None and lr > pr + risk_rise:
        reasons.append(f"fact_risk rose {pr:.3f} -> {lr:.3f}")
    return {"ok": not reasons, "reasons": reasons}


def _main():
    provider = os.environ.get("EVAL_PROVIDER", "groq")
    model = os.environ.get("EVAL_MODEL", "llama-3.3-70b-versatile")
    api_key = os.environ.get("EVAL_API_KEY")
    batch = os.environ.get("EVAL_BATCH", "manual")
    from ..search.providers import DuckDuckGoProvider, SearxngProvider
    llm = {"provider": provider, "model": model, "api_key": api_key}
    providers = [DuckDuckGoProvider(), SearxngProvider()]
    res = asyncio.run(run_eval(llm, providers, batch=batch))
    for r in res:
        print(f"  {r['race']:>5}  risk={r['fact_risk']}  q={r['quality']}  "
              f"faith={r.get('faithfulness')}  cit_r={r.get('citation_recall')}  {r['topic'][:60]}")
    cmp = asyncio.run(compare_to_previous(batch))
    print("compare:", json.dumps({k: (dict((kk, float(vv) if vv is not None else None) for kk, vv in v.items()) if v else None) for k, v in cmp.items()}, default=str))
    gate = regression_gate(cmp)
    print("gate:", gate)
    raise SystemExit(0 if gate["ok"] else 1)   # non-zero exit lets CI fail on a quality regression


if __name__ == "__main__":
    _main()
