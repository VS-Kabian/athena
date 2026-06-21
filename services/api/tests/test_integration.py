"""End-to-end pipeline test against LIVE SearXNG + LIVE Postgres.

Only the LLM calls are stubbed (no API keys needed). Everything else is real:
real HTTP search via SearxngProvider, RRF merge/dedup, DB source+report persistence,
event flow, and report assembly.

Robustness: the deterministic pipeline plumbing (report persisted, status=done, report
format) is always asserted. The source-count assertion is only enforced when a direct
live SearXNG probe confirms the upstream engines returned results this moment — so the
test catches OUR regressions without being flaky against momentary external emptiness.
"""
import httpx
import pytest
from unittest.mock import patch

from athena.db import fetch
from athena.agents.graph import run_research
from athena.search.providers import SearxngProvider
from athena.config import settings


async def _fake_complete(provider, model, messages, api_key=None, **kw):
    joined = " ".join(m.get("content", "") for m in messages)
    if "JSON array" in joined:  # planner decompose/refine prompt
        return '["what is open source software", "benefits of open source software"]'
    return "## Findings\nOpen source software is publicly available source code [1]."


async def _fake_stream(provider, model, messages, api_key=None, **kw):
    body = "## Findings\nOpen source software is publicly available source code [1]."
    od = kw.get("on_delta")
    if od:
        await od(body)
    return body, {"total_tokens": 50}


async def _live_searxng_count(query: str) -> int:
    for _ in range(3):
        try:
            async with httpx.AsyncClient(timeout=10) as c:
                r = await c.get(f"{settings.searxng_url}/search",
                                params={"q": query, "format": "json"})
                n = len(r.json().get("results", []))
                if n:
                    return n
        except Exception:
            pass
    return 0


@pytest.mark.asyncio
async def test_pipeline_end_to_end_live_searxng_and_db():
    rows = await fetch(
        "insert into research_runs(topic,rounds_total,status) values($1,1,'running') returning id",
        "open source software",
    )
    run_id = str(rows[0]["id"])

    with patch("athena.agents.planner.complete", side_effect=_fake_complete), \
         patch("athena.agents.synthesizer.complete", side_effect=_fake_complete), \
         patch("athena.agents.synthesizer.stream_complete", side_effect=_fake_stream):
        md = await run_research(
            run_id, "open source software", rounds=1,
            llm={"provider": "ollama", "model": "stub", "api_key": None},
            providers=[SearxngProvider()], mode="broadcast",
        )

    # --- deterministic pipeline plumbing (always true) ---
    assert md.startswith("# Research Report")
    assert "## Sources" in md

    srcs = await fetch("select * from sources where run_id=$1", run_id)
    rep = await fetch("select markdown from reports where run_id=$1", run_id)
    run = await fetch("select status from research_runs where id=$1", run_id)

    assert len(rep) == 1
    assert "## Sources" in rep[0]["markdown"]
    assert run[0]["status"] == "done"

    # --- live-search proof, only enforced when upstream actually returned results ---
    live = await _live_searxng_count("open source software")
    if live > 0:
        assert len(srcs) >= 1, "SearXNG returned results but pipeline persisted none"
