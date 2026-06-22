"""No blank-report cliff (P0-4 backend): a finish-line DB failure must not show 'Done' over a blank report.
persist_report is retried once; the `done` event carries `report_ready` reflecting whether it persisted,
and on failure includes the fully-synthesized report inline so the client can still render it."""
from contextlib import ExitStack

import pytest
from unittest.mock import patch, AsyncMock

from athena.agents.graph import run_research
from athena.search.base import SearchHit


def _pipeline(events):
    async def rec(rid, ev):
        events.append(ev)
    hits = [SearchHit("u1", "A", "s", 0, "ddg")]
    G = "athena.agents.graph."
    return [
        patch(G + "bus.publish", side_effect=rec),
        patch(G + "bus.is_cancelled", return_value=False),
        patch(G + "arxiv_search", AsyncMock(return_value=[])),
        patch(G + "github_search", AsyncMock(return_value=[])),
        patch(G + "decompose", AsyncMock(return_value=["q1"])),
        patch(G + "extract_entities", AsyncMock(return_value=[])),
        patch(G + "filter_by_relevance", side_effect=lambda t, h: h),
        patch(G + "multi_search", AsyncMock(return_value=hits)),
        patch(G + "persist_sources", AsyncMock()),
        patch(G + "recall", AsyncMock(return_value=[])),
        patch(G + "remember", AsyncMock()),
        patch(G + "select_sources", side_effect=lambda a, n=20, entities=None: list(a.values())),
        patch(G + "fetch_many", AsyncMock(return_value={"u1": "c"})),
        patch(G + "assemble_content", side_effect=lambda s, d: {"u1": "c"}),
        patch(G + "build_evidence", return_value=[{"url": "u1", "text": "c", "score": 0.9}]),
        patch(G + "synthesize_sections", AsyncMock(return_value=("# R [1]", ["u1"], {"u1": "c"}))),
        patch(G + "factcheck", return_value={"risk": 0.0, "total": 1, "unsupported": 0,
                                             "flagged": [], "single_source": [], "consensus": 1.0}),
        patch(G + "select_span", side_effect=lambda t, x, max_chars=400: x),
        patch(G + "verify_report", AsyncMock(return_value=("# R [1]", []))),
    ]


@pytest.mark.asyncio
async def test_done_is_report_ready_false_and_inline_when_persist_fails():
    events = []
    with ExitStack() as st:
        for p in _pipeline(events):
            st.enter_context(p)
        with patch("athena.agents.graph.persist_report",
                   AsyncMock(side_effect=RuntimeError("db down"))) as pr:
            await run_research("r", "t", rounds=1, llm={"provider": "g", "model": "m", "api_key": "k"},
                               providers=[], mode="broadcast")
    assert pr.await_count >= 2                       # retried once before giving up
    done = next(e for e in events if e["type"] == "done")["data"]
    assert done["report_ready"] is False             # NOT a confident "Done" over a blank report
    assert done.get("report", {}).get("markdown")    # report surfaced inline for the client to render


@pytest.mark.asyncio
async def test_done_is_report_ready_true_and_no_inline_when_persist_succeeds():
    events = []
    with ExitStack() as st:
        for p in _pipeline(events):
            st.enter_context(p)
        with patch("athena.agents.graph.persist_report", AsyncMock()):
            await run_research("r", "t", rounds=1, llm={"provider": "g", "model": "m", "api_key": "k"},
                               providers=[], mode="broadcast")
    done = next(e for e in events if e["type"] == "done")["data"]
    assert done["report_ready"] is True
    assert "report" not in done                      # no inline fallback needed on success
