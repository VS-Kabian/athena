"""Master end-to-end test: the whole research system in DEEP mode.

Only the three external network boundaries are stubbed — the LLM (`complete`), web search
(`multi_search` + specialists), and page fetch (`fetch_many`). Everything else runs for real:
the deep-mode controller, relevance filtering, RAG (embeddings + cross-encoder rerank), token
budgeting, span-level citations, fact-checking, quality scoring, Postgres persistence, and the
pgvector cross-run memory round-trip (run A is remembered, then recalled by run B).

Requires a live Postgres (docker compose up -d) with migrations applied (python -m athena.migrate).
"""
import json

import pytest
from unittest.mock import patch, AsyncMock

import athena.db as db
from athena.agents.graph import run_research
from athena.search.base import SearchHit

TOPIC_A = "Retrieval-Augmented Generation (RAG) for enterprise search"
TOPIC_B = "Retrieval-Augmented Generation (RAG) for enterprise search — practical limitations and follow-up"

# A small realistic source pool (on-topic so real relevance filtering keeps them).
POOL = [
    ("https://example.com/rag-overview", "RAG overview for enterprise search",
     "Retrieval-augmented generation grounds LLM answers in retrieved enterprise documents."),
    ("https://example.com/langchain-rag", "Building RAG with LangChain",
     "LangChain provides retrievers and chains to assemble RAG pipelines over private corpora."),
    ("https://example.com/llamaindex-rag", "LlamaIndex for data indexing in RAG",
     "LlamaIndex focuses on indexing and querying documents to feed retrieval-augmented generation."),
    ("https://example.com/rag-eval", "Evaluating RAG systems",
     "Evaluating RAG requires measuring retrieval recall, grounding, and answer faithfulness."),
]

DOCS = {
    "https://example.com/rag-overview":
        "Retrieval-augmented generation (RAG) combines a retriever with a generator. "
        "It grounds large language model answers in retrieved enterprise documents to reduce hallucination. "
        "Enterprise search benefits because answers cite internal sources. "
        "A typical pipeline embeds documents, retrieves top chunks, and synthesizes an answer.",
    "https://example.com/langchain-rag":
        "LangChain provides retrievers, vector store integrations, and chains for RAG. "
        "Developers compose a retriever with a prompt template and an LLM to answer questions. "
        "It supports many vector databases and rerankers for enterprise corpora.",
    "https://example.com/llamaindex-rag":
        "LlamaIndex specializes in indexing and querying documents for retrieval-augmented generation. "
        "It builds node structures over data and exposes query engines. "
        "This makes it well suited to feeding RAG pipelines with structured retrieval.",
    "https://example.com/rag-eval":
        "Evaluating RAG systems means measuring retrieval recall and precision, grounding of claims, "
        "and faithfulness of the generated answer to the retrieved evidence. "
        "Benchmarks combine an LLM judge with citation-support checks.",
}


def _hits():
    return [SearchHit(url, title, snippet, rank=i, provider="ddg",
                      rrf_score=1.0 - i * 0.1, providers=["ddg"])
            for i, (url, title, snippet) in enumerate(POOL)]


async def _fake_multi_search(q, providers, mode="broadcast", k=8):
    return _hits()


async def _fake_specialist(*a, **k):
    return []


async def _fake_fetch_many(urls, limit=20):
    return {u: DOCS.get(u, "") for u in urls if DOCS.get(u)}


async def _fake_planner_complete(*a, **k):
    content = a[2][-1]["content"]
    if "NAMED subjects" in content:
        return '["LangChain", "LlamaIndex"]'
    return '["What is RAG for enterprise search?", "How do LangChain and LlamaIndex compare?", "How is RAG evaluated?"]'


async def _fake_controller_complete(*a, **k):
    content = a[2][-1]["content"]
    if "Round: 1/" in content:
        return '{"action":"drill","questions":["Deeper: retrieval recall in RAG","Deeper: grounding metrics"],"reason":"benchmark gap"}'
    return '{"action":"stop","questions":[],"reason":"coverage is strong"}'


_SYNTH_BODY = ("## Findings\nRAG grounds answers in retrieved enterprise documents [1]. "
               "LangChain and LlamaIndex provide complementary building blocks [2].\n\n"
               "## Conclusion\nRAG is effective for enterprise search when evaluated for grounding.")


async def _fake_synth_complete(*a, **k):
    return _SYNTH_BODY


async def _fake_synth_stream(*a, **k):
    od = k.get("on_delta")
    if od:
        await od(_SYNTH_BODY)
    return _SYNTH_BODY, {"total_tokens": 150, "cost": 0.001}


def _patches(events):
    async def rec(run_id, ev):
        events.append(ev)

    return [
        patch("athena.agents.graph.bus.publish", side_effect=rec),
        patch("athena.agents.graph.multi_search", side_effect=_fake_multi_search),
        patch("athena.agents.graph.arxiv_search", side_effect=_fake_specialist),
        patch("athena.agents.graph.github_search", side_effect=_fake_specialist),
        patch("athena.agents.graph.fetch_many", side_effect=_fake_fetch_many),
        patch("athena.agents.planner.complete", side_effect=_fake_planner_complete),
        patch("athena.agents.controller.complete", side_effect=_fake_controller_complete),
        patch("athena.agents.synthesizer.complete", side_effect=_fake_synth_complete),
        patch("athena.agents.synthesizer.stream_complete", side_effect=_fake_synth_stream),
    ]


async def _seed_run(topic: str) -> str:
    rows = await db.fetch("insert into research_runs(topic,rounds_total,status) "
                          "values($1,3,'running') returning id", topic)
    return str(rows[0]["id"])


@pytest.mark.asyncio
async def test_master_e2e_deep_mode_full_pipeline_with_memory_roundtrip():
    run_a = await _seed_run(TOPIC_A)
    run_b = await _seed_run(TOPIC_B)
    try:
        # ---- RUN A: full deep-mode pipeline, real DB + RAG + memory persist ----
        events_a = []
        from contextlib import ExitStack
        with ExitStack() as stack:
            for p in _patches(events_a):
                stack.enter_context(p)
            report_a = await run_research(run_a, TOPIC_A, rounds=3,
                                          llm={"provider": "groq", "model": "m", "api_key": "k"},
                                          providers=[], mode="broadcast", deep=True)

        types_a = [e["type"] for e in events_a]
        # deep mode: controller reflected and stopped early (round 1 drill -> round 2 stop -> 2 rounds, not 3)
        assert "reflect" in types_a
        assert sum(1 for t in types_a if t == "round_start") == 2
        assert {"source", "synthesizing", "quality", "done"} <= set(types_a)
        assert report_a.startswith("# Research Report")

        # persisted run + report
        run_row = await db.fetch("select status, quality_score from research_runs where id=$1::uuid", run_a)
        assert run_row[0]["status"] == "done" and run_row[0]["quality_score"] is not None
        rep = await db.fetch("select markdown, citations from reports where run_id=$1::uuid", run_a)
        assert rep and "Research Report" in rep[0]["markdown"]

        # span-level citations: at least one non-empty excerpt
        cites = rep[0]["citations"]
        cites = json.loads(cites) if isinstance(cites, str) else cites
        assert cites and any((c.get("excerpt") or "").strip() for c in cites)

        # sources persisted
        srcs = await db.fetch("select count(*) as c from sources where run_id=$1::uuid", run_a)
        assert srcs[0]["c"] >= 1

        # memory: run A was remembered (real pgvector row)
        mem = await db.fetch("select count(*) as c from research_memory where run_id=$1::uuid", run_a)
        assert mem[0]["c"] == 1

        # ---- RUN B: should recall run A via pgvector (real remember -> recall round-trip) ----
        events_b = []
        with ExitStack() as stack:
            for p in _patches(events_b):
                stack.enter_context(p)
            report_b = await run_research(run_b, TOPIC_B, rounds=3,
                                          llm={"provider": "groq", "model": "m", "api_key": "k"},
                                          providers=[], mode="broadcast", deep=True)

        assert report_b.startswith("# Research Report")
        mem_events = [e for e in events_b if e["type"] == "memory"]
        assert mem_events, "run B should emit a memory event recalling prior research"
        related_topics = [r["topic"] for r in mem_events[0]["data"]["related"]]
        assert TOPIC_A in related_topics  # prior run A surfaced as related
    finally:
        # cascade-delete both runs -> removes sources/reports/research_memory probe data
        await db.execute("delete from research_runs where id = any($1::uuid[])", [run_a, run_b])
