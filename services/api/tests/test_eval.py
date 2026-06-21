import pytest
from unittest.mock import patch, AsyncMock
from athena.eval.race import race_score
from athena.agents.quality import quality_score
from athena.db import fetch, execute

@pytest.mark.asyncio
async def test_race_score_parses_judge_json():
    async def fake(*a, **k):
        return 'Here you go: {"comprehensiveness": 8, "depth": 7, "instruction_following": 9, "readability": 8}'
    with patch("athena.eval.race.complete", side_effect=fake):
        r = await race_score("# Report", "topic", {"provider": "groq", "model": "m", "api_key": "k"})
    assert r["overall"] == 8.0
    assert 0 <= r["depth"] <= 10

@pytest.mark.asyncio
async def test_race_score_zero_on_bad_output():
    async def fake(*a, **k): return "not json"
    with patch("athena.eval.race.complete", side_effect=fake):
        r = await race_score("# Report", "topic", {"provider": "groq", "model": "m", "api_key": "k"})
    assert r["overall"] == 0.0

def test_quality_scoring_regression_guard():
    # golden inputs -> expected band; this catches silent drift in the scoring math.
    # NOTE: validation now credits absolute authoritative-source count vs a target (not the
    # validated/discovered ratio), so a strong run with 10 validated sources earns full validation
    # credit and lands ~91 (was ~74 under the old ratio metric).
    q = quality_score(discovered=50, validated=10, hallucination_risk=0.05, rounds=2,
                      avg_relevance=0.65, content_fetched=12)
    assert 85 <= q["score"] <= 95
    q_bad = quality_score(discovered=50, validated=0, hallucination_risk=0.9, rounds=1,
                          avg_relevance=0.2, content_fetched=0)
    assert q_bad["score"] < q["score"]

@pytest.mark.asyncio
async def test_eval_runs_table_persists():
    rows = await fetch("insert into research_runs(topic,status) values('t','done') returning id")
    rid = str(rows[0]["id"])
    await execute("insert into eval_runs(batch,topic,run_id,race_overall,fact_risk,quality_score) "
                  "values($1,$2,$3,$4,$5,$6)", "testbatch", "t", rid, 7.5, 0.1, 72)
    got = await fetch("select race_overall, quality_score from eval_runs where batch='testbatch' limit 1")
    assert float(got[0]["race_overall"]) == 7.5 and got[0]["quality_score"] == 72


@pytest.mark.asyncio
async def test_run_eval_reads_quality_score_from_research_runs_not_reports():
    # regression: reports has NO quality_score column; reading it there raises UndefinedColumnError
    from athena.eval.harness import run_eval
    queries = []

    async def fake_fetch(q, *a):
        queries.append(q)
        if q.lower().startswith("insert into research_runs"):
            return [{"id": "rid-1"}]
        if "from reports" in q:
            return [{"markdown": "# R", "quality_breakdown": "{}"}]
        if "from research_runs" in q:
            return [{"quality_score": 81}]
        return []

    with patch("athena.eval.harness.fetch", side_effect=fake_fetch), \
         patch("athena.eval.harness.execute", AsyncMock()), \
         patch("athena.eval.harness.run_research", AsyncMock(return_value="# R")), \
         patch("athena.eval.harness.race_score", AsyncMock(return_value={"overall": 7.0})):
        res = await run_eval({"provider": "g", "model": "m"}, [], batch="b", topics=["t"])

    reports_q = [q for q in queries if "from reports" in q]
    assert reports_q and all("quality_score" not in q for q in reports_q)   # never selects the bad column
    assert any("from research_runs" in q and "quality_score" in q for q in queries)
    assert res[0]["quality"] == 81
