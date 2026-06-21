"""MASTER end-to-end test — the whole ATHENA system in one run.

Stubs ONLY the external boundaries (LLM `complete`, web search, page fetch). Everything else runs
for real: planner decompose/refine, deep-mode controller, relevance filter, the credibility model,
mid-loop reading, source selection, RAG (embeddings + reranker), span citations, synthesis,
two-model verification, cross-source corroboration fact-check, quality scoring, Postgres
persistence, and the pgvector memory write. Requires a live DB (docker compose up -d + migrate).
"""
import json

import pytest
from unittest.mock import patch, AsyncMock
from contextlib import ExitStack

import athena.db as db
from athena.agents.graph import run_research
from athena.search.base import SearchHit

TOPIC = "Retrieval-Augmented Generation (RAG) for enterprise search"

POOL = [
    ("https://arxiv.org/abs/2312.10997", "A Survey of Retrieval-Augmented Generation",
     "Retrieval-augmented generation grounds language model answers in retrieved documents."),
    ("https://example-blog.com/rag-guide", "Building RAG with LangChain",
     "LangChain provides retrievers and chains to build RAG pipelines over enterprise data."),
]
DOCS = {
    "https://arxiv.org/abs/2312.10997":
        "Retrieval-augmented generation (RAG) combines a retriever with a generator to ground answers "
        "in retrieved enterprise documents and reduce hallucination. It improves factual accuracy.",
    "https://example-blog.com/rag-guide":
        "LangChain offers retrievers, vector stores, and chains so developers can assemble RAG "
        "pipelines over private corpora and answer questions with citations.",
}


def _hits():
    return [SearchHit(url, title, snippet, rank=i, provider="ddg", rrf_score=1.0 - i * 0.1, providers=["ddg"])
            for i, (url, title, snippet) in enumerate(POOL)]


async def _fake_search(q, providers, mode="broadcast", k=8):
    return _hits()


async def _fake_none(*a, **k):
    return []


async def _fake_fetch_many(urls, limit=20):
    return {u: DOCS[u] for u in urls if u in DOCS}


async def _fake_planner(*a, **k):
    content = a[2][-1]["content"]
    if "NAMED subjects" in content:
        return '["RAG", "LangChain"]'
    return '["What is RAG for enterprise search?", "How does RAG reduce hallucination?", "RAG limitations?"]'


async def _fake_reflect(*a, **k):
    return '{"action":"continue","questions":["Deeper: RAG grounding metrics"],"reason":"need more depth"}'


_REPORT_BODY = ("## Findings\nRAG grounds answers in retrieved enterprise documents [1]. "
                "LangChain enables building RAG pipelines [2].\n\n## Conclusion\nRAG improves factual accuracy.")


async def _fake_synth(*a, **k):
    return _REPORT_BODY


async def _fake_stream(*a, **k):
    od = k.get("on_delta")
    if od:
        await od(_REPORT_BODY)               # exercise the streaming path
    return _REPORT_BODY, {"prompt_tokens": 120, "completion_tokens": 90, "total_tokens": 210, "cost": 0.0012}


async def _fake_verify(*a, **k):
    return '[{"n":1,"verdict":"supported","correction":""},{"n":2,"verdict":"weak","correction":""}]'


def _patches(events):
    async def rec(rid, ev):
        events.append(ev)
    return [
        patch("athena.agents.graph.bus.publish", side_effect=rec),
        patch("athena.agents.graph.bus.is_cancelled", return_value=False),
        patch("athena.agents.graph.multi_search", side_effect=_fake_search),
        patch("athena.agents.graph.arxiv_search", side_effect=_fake_none),
        patch("athena.agents.graph.github_search", side_effect=_fake_none),
        patch("athena.agents.graph.fetch_many", side_effect=_fake_fetch_many),
        patch("athena.agents.planner.complete", side_effect=_fake_planner),
        patch("athena.agents.controller.complete", side_effect=_fake_reflect),
        patch("athena.agents.synthesizer.complete", side_effect=_fake_synth),
        patch("athena.agents.synthesizer.stream_complete", side_effect=_fake_stream),
        patch("athena.agents.verifier.complete", side_effect=_fake_verify),
    ]


@pytest.mark.asyncio
async def test_master_full_system_end_to_end():
    rows = await db.fetch("insert into research_runs(topic,rounds_total,status) values($1,2,'running') returning id", TOPIC)
    run_id = str(rows[0]["id"])
    try:
        events = []
        with ExitStack() as st:
            for p in _patches(events):
                st.enter_context(p)
            report = await run_research(run_id, TOPIC, rounds=2,
                                        llm={"provider": "deepseek", "model": "writer", "api_key": "k"},
                                        verifier={"provider": "groq", "model": "verifier", "api_key": "k"},
                                        providers=[], mode="broadcast", deep=True)

        types = [e["type"] for e in events]
        # every major phase fired, including mid-loop reading, streaming, usage + two-model verification
        for needed in ("round_start", "source", "reading", "validated", "fetching",
                       "synthesizing", "report_delta", "usage", "verify", "quality", "done"):
            assert needed in types, f"missing '{needed}' event"
        assert report.startswith("# Research Report")

        # persisted run + report
        run_row = await db.fetch("select status, quality_score from research_runs where id=$1::uuid", run_id)
        assert run_row[0]["status"] == "done" and run_row[0]["quality_score"] is not None
        rep = await db.fetch("select markdown, citations from reports where run_id=$1::uuid", run_id)
        assert rep and "Research Report" in rep[0]["markdown"]
        cites = rep[0]["citations"]
        cites = json.loads(cites) if isinstance(cites, str) else cites
        assert cites and any((c.get("excerpt") or "").strip() for c in cites)   # span citations

        # credibility model worked: the arXiv source is persisted AND validated
        srcs = await db.fetch("select url, validated from sources where run_id=$1::uuid", run_id)
        assert any("arxiv.org" in s["url"] and s["validated"] for s in srcs), "authoritative source not validated"

        # memory: this run was remembered (pgvector write)
        mem = await db.fetch("select count(*) as c from research_memory where run_id=$1::uuid", run_id)
        assert mem[0]["c"] == 1
    finally:
        await db.execute("delete from research_runs where id=$1::uuid", run_id)
