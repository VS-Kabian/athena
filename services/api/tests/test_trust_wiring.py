"""Integration: the research loop wires the trust ledger end to end — it emits coverage/entail/
urlhealth events, runs entailment on cited claims, and persists per-claim verdicts."""
import json
from contextlib import ExitStack
import pytest
from unittest.mock import patch, AsyncMock

from athena.agents.graph import run_research
from athena.search.base import SearchHit

REPORT = "# Report\n\nThis is claim number one about the chosen topic [1].\n\n## Sources\n1. https://a.com"
SRC = {"https://a.com": "Source text that clearly supports claim number one about the topic."}


@pytest.mark.asyncio
async def test_pipeline_emits_trust_events_and_persists_claims():
    events = []
    async def fake_publish(run_id, ev): events.append(ev)
    captured = {}
    async def fake_persist_claims(run_id, verdicts): captured["verdicts"] = verdicts
    async def fake_complete(provider, model, messages, api_key, **kw):
        return json.dumps([{"n": 1, "verdict": "supported", "confidence": 0.9, "conflict": False}])
    hits = [SearchHit("https://a.com", "A", "s", 0, "ddg")]

    G = "athena.agents.graph."
    patches = {
        G + "bus.publish": patch(G + "bus.publish", side_effect=fake_publish),
        G + "bus.is_cancelled": patch(G + "bus.is_cancelled", return_value=False),
        G + "arxiv_search": patch(G + "arxiv_search", AsyncMock(return_value=[])),
        G + "github_search": patch(G + "github_search", AsyncMock(return_value=[])),
        G + "filter_by_relevance": patch(G + "filter_by_relevance", side_effect=lambda t, h: h),
        G + "decompose": patch(G + "decompose", AsyncMock(return_value=["q1"])),
        G + "extract_entities": patch(G + "extract_entities", AsyncMock(return_value=["EntityA"])),
        G + "multi_search": patch(G + "multi_search", AsyncMock(return_value=hits)),
        G + "persist_sources": patch(G + "persist_sources", AsyncMock()),
        G + "recall": patch(G + "recall", AsyncMock(return_value=[])),
        G + "remember": patch(G + "remember", AsyncMock()),
        G + "select_sources": patch(G + "select_sources", side_effect=lambda a, n=20, entities=None: list(a.values())),
        G + "fetch_many": patch(G + "fetch_many", AsyncMock(return_value={"https://a.com": "content"})),
        G + "assemble_content": patch(G + "assemble_content", side_effect=lambda s, d: {"https://a.com": "content"}),
        G + "build_evidence": patch(G + "build_evidence", return_value=[{"url": "https://a.com", "text": "content", "score": 0.9}]),
        G + "synthesize_sections": patch(G + "synthesize_sections", AsyncMock(return_value=(REPORT, ["https://a.com"], SRC))),
        G + "factcheck": patch(G + "factcheck", return_value={"risk": 0.0, "total": 1, "unsupported": 0,
                                                              "flagged": [], "single_source": [], "consensus": 1.0}),
        G + "select_span": patch(G + "select_span", side_effect=lambda t, x, max_chars=400: x),
        G + "check_urls": patch(G + "check_urls", AsyncMock(return_value={"https://a.com": {"status": "live", "code": 200}})),
        G + "persist_claims": patch(G + "persist_claims", side_effect=fake_persist_claims),
        G + "persist_report": patch(G + "persist_report", AsyncMock()),
        "athena.agents.entail.complete": patch("athena.agents.entail.complete", side_effect=fake_complete),
    }
    with ExitStack() as stack:
        for p in patches.values():
            stack.enter_context(p)
        report = await run_research("rt", "topic", rounds=1,
                                    llm={"provider": "g", "model": "m", "api_key": "k"},
                                    providers=[], mode="broadcast")

    types = [e["type"] for e in events]
    assert "coverage" in types          # #1 coverage ledger streamed
    assert "entail" in types            # #2 entailment summary streamed
    assert "urlhealth" in types         # #4 link-liveness streamed
    assert report.startswith("# Report")

    ent = next(e for e in events if e["type"] == "entail")["data"]
    assert ent["engine"] == "entailment" and ent["supported"] == 1
    # #2/#3 per-claim verdicts persisted as the audit trail
    assert captured.get("verdicts") and captured["verdicts"][0]["verdict"] == "supported"

    cov = next(e for e in events if e["type"] == "coverage")["data"]
    assert "cells" in cov and any(c["question"] == "q1" for c in cov["cells"])
