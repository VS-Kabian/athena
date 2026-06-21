import pytest
from unittest.mock import patch, AsyncMock

from athena import memory


@pytest.mark.asyncio
async def test_remember_embeds_and_inserts():
    captured = {}

    async def fake_exec(q, *args):
        captured["q"], captured["args"] = q, args

    with patch("athena.memory.embed_passages", return_value=[[0.1, 0.2, 0.3]]), \
         patch("athena.memory.execute", side_effect=fake_exec):
        await memory.remember("run1", "RAG systems", "# Research Report: RAG\n\nBody text here.")

    assert "insert into research_memory" in captured["q"]
    assert captured["args"][0] == "run1" and captured["args"][1] == "RAG systems"
    assert captured["args"][3].startswith("[")              # pgvector literal
    assert "Body text here" in captured["args"][2]          # title line stripped, body kept


@pytest.mark.asyncio
async def test_remember_noop_when_embedding_empty():
    called = {"n": 0}

    async def fake_exec(q, *a):
        called["n"] += 1

    with patch("athena.memory.embed_passages", return_value=[]), \
         patch("athena.memory.execute", side_effect=fake_exec):
        await memory.remember("r", "t", "md")
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_recall_returns_prior_summaries():
    rows = [{"run_id": "r0", "topic": "old topic", "summary": "prior summary", "similarity": 0.8}]
    with patch("athena.memory.embed_query", return_value=[0.1, 0.2, 0.3]), \
         patch("athena.memory.fetch", AsyncMock(return_value=rows)):
        out = await memory.recall("new topic", k=3)
    assert out and out[0]["topic"] == "old topic" and out[0]["similarity"] == 0.8


@pytest.mark.asyncio
async def test_recall_excludes_current_run():
    seen = {}

    async def fake_fetch(q, *a):
        seen["q"], seen["a"] = q, a
        return []

    with patch("athena.memory.embed_query", return_value=[0.1]), \
         patch("athena.memory.fetch", side_effect=fake_fetch):
        await memory.recall("t", k=2, exclude_run_id="run1")
    assert "run_id <> $2::uuid" in seen["q"] and "run1" in seen["a"]


@pytest.mark.asyncio
async def test_recall_applies_similarity_floor():
    seen = {}

    async def fake_fetch(q, *a):
        seen["q"], seen["a"] = q, a
        return []

    with patch("athena.memory.embed_query", return_value=[0.1, 0.2]), \
         patch("athena.memory.fetch", side_effect=fake_fetch):
        await memory.recall("t", k=3, min_similarity=0.7)
    assert "1 - (embedding <=> $1::vector) >= " in seen["q"]
    assert 0.7 in seen["a"]
