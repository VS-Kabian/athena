"""Orchestrator behavior: coverage-driven stop (Task 1) and parallel metered sub-agents (Task 2)."""
import asyncio
from contextlib import ExitStack
import pytest
from unittest.mock import patch, AsyncMock

from athena.agents import graph as G
from athena.agents.graph import run_research, _sufficient, _subagent, _read_top, _heartbeat
from athena.agents.coverage import is_complete
from athena.search.base import SearchHit


def _cov(*scores):
    return {"cells": [{"question": f"q{i}", "score": s} for i, s in enumerate(scores)], "overall": 0.0}


def _hits(n_validated):
    return {f"u{i}": {"validated": i < n_validated} for i in range(max(n_validated, 6))}


# ── Task 1: coverage-driven stop ──
def test_is_complete_requires_every_cell_covered():
    assert is_complete(_cov(0.8, 0.6)) is True
    assert is_complete(_cov(0.8, 0.2)) is False       # one weak cell -> not complete
    assert is_complete({"cells": []}) is False        # nothing measured yet


def test_sufficient_blocks_stop_with_under_covered_cell():
    # plenty of validated sources, but one sub-question is under-covered -> must NOT stop (drill it)
    assert _sufficient(3, _hits(8), ["a", "b"], new_this_round=3, coverage=_cov(0.9, 0.2)) is False


def test_sufficient_keeps_going_while_new_sources_arrive():
    # even with complete coverage, a round that found NEW sources isn't a plateau -> keep using the
    # round budget (adaptive planning widens the plan rather than quitting early)
    assert _sufficient(3, _hits(8), ["a", "b"], new_this_round=3, coverage=_cov(0.9, 0.7)) is False
    # ...but once a round adds nothing new (plateau), it's truly done
    assert _sufficient(3, _hits(8), ["a", "b"], new_this_round=0, coverage=_cov(0.9, 0.7)) is True


def test_sufficient_plateau_stops_even_with_gap():
    # a round that added nothing new can't improve coverage -> stop anyway (bounded loop)
    assert _sufficient(3, _hits(8), ["a", "b"], new_this_round=0, coverage=_cov(0.9, 0.1)) is True


def test_sufficient_never_stops_before_min_rounds():
    assert _sufficient(1, _hits(8), ["a", "b"], new_this_round=2, coverage=_cov(0.9, 0.9)) is False


def test_sufficient_complete_but_too_few_validated_keeps_going():
    # coverage complete yet validated below target -> not sufficient
    assert _sufficient(3, _hits(2), ["a", "b"], new_this_round=2, coverage=_cov(0.9, 0.9)) is False


# ── Task 2: parallel metered sub-agents + breadth-first reading ──
@pytest.mark.asyncio
async def test_subagent_returns_relevance_filtered_hits_for_its_question():
    raw = [SearchHit("https://x", "X", "s", 0, "ddg")]
    filtered = [SearchHit("https://x", "X", "s", 0, "ddg", relevance=0.8)]
    sem = asyncio.Semaphore(2)
    with patch.object(G, "_fanout_search", new=AsyncMock(return_value=raw)), \
         patch.object(G, "filter_by_relevance", return_value=filtered):
        q, hits = await _subagent("topic", "myq", [], [], "broadcast", 8, sem)
    assert q == "myq" and hits == filtered


@pytest.mark.asyncio
async def test_subagent_isolates_its_own_failure():
    sem = asyncio.Semaphore(2)
    with patch.object(G, "_fanout_search", new=AsyncMock(side_effect=RuntimeError("provider down"))):
        q, hits = await _subagent("topic", "myq", [], [], "broadcast", 8, sem)
    assert q == "myq" and hits == []          # failure isolated -> empty, never raises


@pytest.mark.asyncio
async def test_read_top_reads_at_least_one_per_subquestion(monkeypatch):
    # global top-N would starve a low-relevance sub-question; breadth-first must still read it
    monkeypatch.setattr(G, "READ_PER_ROUND", 2)
    monkeypatch.setattr(G, "MIN_READ_PER_SUBQ", 1)

    def _e(url, subq, rel):
        return {"hit": SearchHit(url, "t", "s", 0, "p"), "subq": subq, "relevance": rel, "content": ""}

    all_hits = {"a1": _e("https://a1", "qa", 0.9), "a2": _e("https://a2", "qa", 0.8),
                "a3": _e("https://a3", "qa", 0.7), "b1": _e("https://b1", "qb", 0.2)}

    async def fake_fetch_many(urls, limit=12):
        return {u: "content" for u in urls}

    with patch.object(G, "fetch_many", side_effect=fake_fetch_many), \
         patch.object(G.bus, "publish", new=AsyncMock()):
        await _read_top("r", all_hits, 1)

    assert all_hits["b1"]["content"] == "content"                                  # weak cell not starved
    assert any(all_hits[k]["content"] == "content" for k in ("a1", "a2", "a3"))    # strong cell read too


@pytest.mark.asyncio
async def test_adaptive_planning_appends_a_new_facet_when_scope_is_covered():
    # when the current facets are all covered (no weak cells), the planner widens the plan with a NEW
    # facet (append-only) and the next round researches it — instead of stopping flat.
    events = []
    async def pub(rid, ev): events.append(ev)
    hits = [SearchHit("https://a.com", "A", "s", 0, "ddg")]
    P = "athena.agents.graph."
    patches = {
        "bus.publish": patch(P + "bus.publish", side_effect=pub),
        "is_cancelled": patch(P + "bus.is_cancelled", return_value=False),
        "arxiv": patch(P + "arxiv_search", AsyncMock(return_value=[])),
        "github": patch(P + "github_search", AsyncMock(return_value=[])),
        "filter": patch(P + "filter_by_relevance", side_effect=lambda t, h: h),
        "decompose": patch(P + "decompose", AsyncMock(return_value=["q1"])),
        "entities": patch(P + "extract_entities", AsyncMock(return_value=[])),
        "multi": patch(P + "multi_search", AsyncMock(return_value=hits)),
        "weak": patch(P + "weakest_questions", return_value=[]),          # pretend everything is covered
        "expand": patch(P + "expand_facets", AsyncMock(return_value=["NEW-FACET"])),
        "persist_s": patch(P + "persist_sources", AsyncMock()),
        "recall": patch(P + "recall", AsyncMock(return_value=[])),
        "remember": patch(P + "remember", AsyncMock()),
        "select": patch(P + "select_sources", side_effect=lambda a, n=20, entities=None: list(a.values())),
        "fetch": patch(P + "fetch_many", AsyncMock(return_value={"https://a.com": "content"})),
        "assemble": patch(P + "assemble_content", side_effect=lambda s, d: {"https://a.com": "content"}),
        "evidence": patch(P + "build_evidence", return_value=[{"url": "https://a.com", "text": "c", "score": 0.9}]),
        "synth": patch(P + "synthesize_sections", AsyncMock(return_value=("# Report", ["https://a.com"], {"https://a.com": "c"}))),
        "factcheck": patch(P + "factcheck", return_value={"risk": 0.0, "total": 1, "unsupported": 0, "flagged": []}),
        "span": patch(P + "select_span", side_effect=lambda t, x, max_chars=400: x),
        "persist_r": patch(P + "persist_report", AsyncMock()),
    }
    with ExitStack() as stack:
        for p in patches.values():
            stack.enter_context(p)
        await run_research("r", "topic", rounds=2,
                           llm={"provider": "g", "model": "m", "api_key": "k"}, providers=[], mode="broadcast")
    expand_ev = [e for e in events if e["type"] == "plan_expand"]
    assert expand_ev and "NEW-FACET" in expand_ev[0]["data"]["added"]
    # round 2 then researches the newly added facet
    round2 = [e for e in events if e["type"] == "round_start" and e["data"]["round"] == 2]
    assert round2 and round2[0]["data"]["questions"] == ["NEW-FACET"]


@pytest.mark.asyncio
async def test_heartbeat_publishes_keepalive_then_stops_on_cancel():
    # the SSE keepalive must emit while the run is alive and shut down cleanly when cancelled
    events = []
    async def pub(rid, ev): events.append(ev)
    with patch.object(G.bus, "publish", side_effect=pub):
        task = asyncio.create_task(_heartbeat("r", interval=0.01))
        await asyncio.sleep(0.035)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert any(e["type"] == "heartbeat" for e in events)
