import json
from ..db import execute
from ..search.base import url_hash

async def persist_sources(run_id: str, all_hits: dict):
    for entry in all_hits.values():
        h = entry["hit"]
        await execute(
            """insert into sources(run_id,url,url_hash,title,domain,source_type,round,rrf_score,trust_score,validated)
               values($1,$2,$3,$4,$5,$6,$7,$8,$9,$10) on conflict (run_id,url_hash) do nothing""",
            run_id, h.url, url_hash(h.url), h.title,
            h.url.split('/')[2] if '://' in h.url else '',
            entry.get("source_type", "web"), entry["round"], h.rrf_score,
            entry.get("trust", 0.5), entry.get("validated", False))


async def persist_claims(run_id: str, verdicts: list[dict]):
    """Persist per-claim entailment verdicts (the audit trail) to the claims table. Best-effort and
    bounded; a DB hiccup here must never sink an already-synthesized report."""
    for v in (verdicts or [])[:200]:
        try:
            conf = float(v.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            conf = 0.0
        await execute(
            "insert into claims(run_id, text, verdict, confidence, conflict) values($1,$2,$3,$4,$5)",
            run_id, str(v.get("claim", ""))[:4000], str(v.get("verdict", "unverified")),
            conf, bool(v.get("conflict", False)))


async def persist_report(run_id: str, markdown: str, quality_score: int | None = None,
                         quality_breakdown: dict | None = None, citations: list | None = None,
                         flagged: list | None = None, trust: dict | None = None):
    await execute(
        "insert into reports(run_id, markdown, quality_breakdown, citations, flagged, trust) "
        "values($1,$2,$3::jsonb,$4::jsonb,$5::jsonb,$6::jsonb)",
        run_id, markdown, json.dumps(quality_breakdown or {}),
        json.dumps(citations or []), json.dumps(flagged or []), json.dumps(trust or {}))
    # only the first terminal write wins: guard on status='running' so a cancel racing the finish
    # line can't be flipped back to 'done' (and vice-versa).
    await execute("update research_runs set status='done', quality_score=$2, completed_at=now() "
                  "where id=$1 and status='running'", run_id, quality_score)
