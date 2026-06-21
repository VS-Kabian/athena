import json, pytest
from athena.db import fetch
from athena.agents.persist import persist_report

@pytest.mark.asyncio
async def test_persist_report_stores_breakdown_citations_flagged():
    rows = await fetch("insert into research_runs(topic,status) values('t','running') returning id")
    rid = str(rows[0]["id"])
    await persist_report(rid, "# R", 80,
                         {"coverage": 18, "hallucination_risk": 0.1},
                         [{"n": 1, "url": "https://a.com", "title": "A", "excerpt": "ev"}],
                         ["a flagged claim"])
    rep = await fetch("select quality_breakdown, citations, flagged from reports where run_id=$1", rid)
    qb = rep[0]["quality_breakdown"]; cit = rep[0]["citations"]; fl = rep[0]["flagged"]
    qb = json.loads(qb) if isinstance(qb, str) else qb
    cit = json.loads(cit) if isinstance(cit, str) else cit
    fl = json.loads(fl) if isinstance(fl, str) else fl
    assert qb["coverage"] == 18
    assert cit[0]["url"] == "https://a.com" and cit[0]["excerpt"] == "ev"
    assert fl == ["a flagged claim"]
