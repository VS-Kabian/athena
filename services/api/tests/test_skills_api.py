"""Tests for the agent-skill endpoints (/api/rerank, /api/verify).

Hermetic: the cross-encoder, the key vault, and the verifier LLM are all mocked, so these run
with no model download, no DB key, and no network — fast and deterministic.
"""
import pytest
from unittest.mock import AsyncMock
from httpx import AsyncClient, ASGITransport

from athena.api.app import app


def _client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


@pytest.mark.asyncio
async def test_rerank_sorts_by_score(monkeypatch):
    monkeypatch.setattr("athena.api.skills._rerank", lambda q, ps: [0.1, 0.9, 0.5])
    async with _client() as c:
        r = await c.post("/api/rerank", json={"query": "x", "passages": ["a", "b", "c"]})
    assert r.status_code == 200
    ranked = r.json()["ranked"]
    assert [x["text"] for x in ranked] == ["b", "c", "a"]   # 0.9 > 0.5 > 0.1
    assert ranked[0]["score"] == 0.9 and ranked[0]["index"] == 1


@pytest.mark.asyncio
async def test_rerank_top_k(monkeypatch):
    monkeypatch.setattr("athena.api.skills._rerank", lambda q, ps: [0.1, 0.9, 0.5])
    async with _client() as c:
        r = await c.post("/api/rerank", json={"query": "x", "passages": ["a", "b", "c"], "top_k": 2})
    ranked = r.json()["ranked"]
    assert [x["text"] for x in ranked] == ["b", "c"] and r.json()["count"] == 2


@pytest.mark.asyncio
async def test_rerank_empty():
    async with _client() as c:
        r = await c.post("/api/rerank", json={"query": "x", "passages": []})
    assert r.status_code == 200 and r.json()["ranked"] == []


@pytest.mark.asyncio
async def test_rerank_falls_back_when_reranker_unavailable(monkeypatch):
    monkeypatch.setattr("athena.api.skills._rerank", lambda q, ps: [])   # reranker down
    async with _client() as c:
        r = await c.post("/api/rerank", json={"query": "x", "passages": ["a", "b"]})
    ranked = r.json()["ranked"]
    assert {x["text"] for x in ranked} == {"a", "b"} and all(x["score"] == 0.0 for x in ranked)


@pytest.mark.asyncio
async def test_verify_corrects_contradicted_claim(monkeypatch):
    monkeypatch.setattr("athena.api.skills.get_key", AsyncMock(return_value="fake-key"))
    fake = '[{"n":1,"verdict":"contradicted","correction":"The sky is blue [1]."}]'
    monkeypatch.setattr("athena.agents.verifier.complete", AsyncMock(return_value=fake))
    body = {"report_markdown": "The sky is green [1].\n\n## Sources\n[1] x",
            "sources": [{"text": "The sky is blue."}], "provider": "gemini", "model": "gemini-2.5-flash"}
    async with _client() as c:
        r = await c.post("/api/verify", json=body)
    assert r.status_code == 200
    d = r.json()
    assert "blue" in d["report_markdown"] and d["flagged"] == 1


@pytest.mark.asyncio
async def test_verify_unknown_provider_404():
    async with _client() as c:
        r = await c.post("/api/verify", json={"report_markdown": "x [1].", "sources": [], "provider": "nope"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_verify_no_key_degrades_gracefully(monkeypatch):
    monkeypatch.setattr("athena.api.skills.get_key", AsyncMock(return_value=None))
    body = {"report_markdown": "Claim [1].", "sources": [{"text": "src"}], "provider": "gemini"}
    async with _client() as c:
        r = await c.post("/api/verify", json=body)
    assert r.status_code == 200
    d = r.json()
    assert d["flagged"] == 0 and "no saved key" in d.get("note", "")


@pytest.mark.asyncio
async def test_rerank_rejects_too_many_passages():
    """Bounded input — can't be used as a memory/CPU DoS primitive."""
    async with _client() as c:
        r = await c.post("/api/rerank", json={"query": "x", "passages": ["a"] * 501})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_verify_rejects_oversize_report():
    async with _client() as c:
        r = await c.post("/api/verify", json={"report_markdown": "x" * 200_001, "sources": []})
    assert r.status_code == 422
