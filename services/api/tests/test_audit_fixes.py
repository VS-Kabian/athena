"""Regression tests for audit fixes F-004, F-006, F-018 (the integrator-owned set)."""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch


# ── F-006: FIFO eviction must WAKE a blocked subscriber, not orphan it ──
@pytest.mark.asyncio
async def test_eviction_unblocks_subscriber(monkeypatch):
    import athena.api.events as ev
    monkeypatch.setattr(ev, "_MAX_RUNS", 1)
    bus = ev.EventBus()
    await bus.publish("A", {"type": "status", "data": {}})
    seen = []

    async def consume():
        async for e in bus.subscribe("A"):
            seen.append(e)

    task = asyncio.create_task(consume())
    await asyncio.sleep(0.05)                                   # let it drain + block on wait()
    await bus.publish("B", {"type": "status", "data": {}})      # evicts A's backlog
    await asyncio.wait_for(task, timeout=2)                     # must terminate, not hang forever
    assert any(e["type"] == "status" for e in seen)


# ── F-004: a finalized run must not be flipped by a racing terminal write ──
@pytest.mark.asyncio
async def test_persist_report_does_not_override_cancelled():
    from athena.db import fetch
    from athena.agents.persist import persist_report
    rows = await fetch("insert into research_runs(topic,status) values('t','cancelled') returning id")
    rid = str(rows[0]["id"])
    await persist_report(rid, "# R", 90, {}, [], [])
    row = await fetch("select status from research_runs where id=$1", rid)
    assert row[0]["status"] == "cancelled"                     # NOT flipped to 'done'


# ── F-018: complete() returns "" on empty choices and never None ──
@pytest.mark.asyncio
async def test_complete_empty_choices_returns_empty_string():
    from athena.gateway import llm

    class _Resp:
        choices = []

    with patch("athena.gateway.llm.acompletion", AsyncMock(return_value=_Resp())):
        out = await llm.complete("groq", "m", [{"role": "user", "content": "hi"}], "k")
    assert out == ""


# ── F-007 (re-verify round 2): cache overflow must not drop a still-needed cached text → KeyError ──
def test_rerank_cache_overflow_does_not_keyerror(monkeypatch):
    import athena.search.relevance as rel
    rel._SCORE_CACHE.clear()
    monkeypatch.setattr(rel, "_SCORE_CACHE_CAP", 2)
    monkeypatch.setattr(rel, "rerank", lambda q, ts: [0.5] * len(ts))
    rel._rerank_cached("t", ["A", "X", "Y"])      # cache now holds 3 entries (> cap 2)
    out = rel._rerank_cached("t", ["A", "B"])      # references cached "A"; overflow clears at top
    assert out == [0.5, 0.5]                        # no KeyError, "A" correctly re-scored
    rel._SCORE_CACHE.clear()
