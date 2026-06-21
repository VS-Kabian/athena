"""MCP server exposing ATHENA's deep-research engine as Model Context Protocol tools.

Run it (stdio transport):  python -m athena.mcp.server

The Google ADK agent (../../../agent/) connects to this server via MCPToolset and calls
``deep_research``. This is a THIN wrapper over the existing FastAPI backend — it reuses the entire
hardened pipeline (multi-round search, mid-loop reading, two-model verification, fact-check, quality
scoring) instead of reimplementing any of it.
"""
import asyncio
import os

import httpx
from mcp.server.fastmcp import FastMCP

from ..gateway.llm import redact_keys

API_URL = os.environ.get("ATHENA_API_URL", "http://localhost:7000").rstrip("/")
API_TOKEN = os.environ.get("ATHENA_API_TOKEN", "")
DEFAULT_PROVIDERS = ["ddg", "searxng", "tavily"]
_TERMINAL = {"done", "failed", "cancelled"}

mcp = FastMCP("athena-research")


def _headers() -> dict:
    return {"Authorization": f"Bearer {API_TOKEN}"} if API_TOKEN else {}


async def deep_research(topic: str, provider: str = "gemini",
                        model: str = "gemini-2.5-flash",
                        rounds: int = 2, deep: bool = False) -> dict:
    """Run an autonomous multi-round web research pass on ``topic`` and return a cited markdown report.

    The ATHENA engine decomposes the question, searches multiple providers, reads sources, reflects,
    synthesizes a report, and fact-checks it. The provider API key is read from the backend's encrypted
    vault (set it once in the ATHENA UI), so it is never passed through this tool.

    Args:
        topic: the research question or topic.
        provider: LLM provider id (e.g. "groq", "deepseek", "gemini").
        model: model id for that provider.
        rounds: number of research rounds (1-5).
        deep: enable the reflective deep-research controller.

    Returns:
        dict with run_id, status, quality_score (0-100), report_markdown, and top_sources.
    """
    body = {
        "topic": topic, "rounds": max(1, min(int(rounds), 5)), "deep": bool(deep),
        "llm": {"provider": provider, "model": model},   # no api_key -> backend uses the stored vault key
        "search": {"providers": DEFAULT_PROVIDERS, "mode": "broadcast", "keys": {}},
    }
    try:
        async with httpx.AsyncClient(timeout=30, headers=_headers()) as c:
            r = await c.post(f"{API_URL}/api/research", json=body)
            if r.status_code != 200:
                return {"error": f"failed to start research ({r.status_code}): {r.text[:200]}"}
            run_id = r.json().get("run_id")
            if not run_id:
                return {"error": "backend did not return a run_id"}
            errors = 0
            for _ in range(200):                      # poll to a terminal state (~200 * 3s = 10 min ceiling)
                await asyncio.sleep(3)
                resp = await c.get(f"{API_URL}/api/research/{run_id}")
                if resp.status_code == 404:
                    return {"error": "run not found", "run_id": run_id}
                if resp.status_code != 200:
                    errors += 1
                    if errors >= 5:                    # don't poll a broken backend for 10 minutes
                        return {"error": f"backend errored while polling ({resp.status_code})", "run_id": run_id}
                    continue
                errors = 0
                d = resp.json()
                status = ((d.get("run") or {}).get("status")) or ""
                if status in _TERMINAL:
                    srcs = d.get("sources") or []
                    return {
                        "run_id": run_id, "status": status,
                        "quality_score": (d.get("run") or {}).get("quality_score"),
                        "report_markdown": d.get("report") or "",
                        "top_sources": [{"title": s.get("title"), "url": s.get("url"),
                                         "validated": s.get("validated")} for s in srcs[:10]],
                    }
            return {"error": "research timed out", "run_id": run_id}
    except Exception as e:
        return {"error": redact_keys(f"deep_research failed: {str(e)[:200]}")}


async def get_report(run_id: str) -> dict:
    """Fetch a finished ATHENA research report by run_id (markdown + sources)."""
    try:
        async with httpx.AsyncClient(timeout=30, headers=_headers()) as c:
            resp = await c.get(f"{API_URL}/api/research/{run_id}")
            if resp.status_code == 404:
                return {"error": "run not found"}
            d = resp.json()
            return {"run_id": run_id, "report_markdown": d.get("report") or "",
                    "sources": d.get("sources") or []}
    except Exception as e:
        return {"error": redact_keys(f"get_report failed: {str(e)[:200]}")}


async def rerank_sources(query: str, passages: list[str], top_k: int = 0) -> dict:
    """RERANK skill — score each passage's relevance to ``query`` with ATHENA's cross-encoder and
    return them sorted best-first. Lets the ADK agent sharpen a candidate set without a full run.

    Args:
        query: the question/topic to rank against.
        passages: candidate snippets/sources to score.
        top_k: keep only the top_k results (0 = keep all).

    Returns:
        dict {"ranked": [{"index", "text", "score"}], "count": int} or {"error": ...}.
    """
    body: dict = {"query": query, "passages": passages}
    if top_k and top_k > 0:
        body["top_k"] = int(top_k)
    try:
        async with httpx.AsyncClient(timeout=60, headers=_headers()) as c:
            r = await c.post(f"{API_URL}/api/rerank", json=body)
            if r.status_code != 200:
                return {"error": f"rerank failed ({r.status_code}): {r.text[:200]}"}
            return r.json()
    except Exception as e:
        return {"error": redact_keys(f"rerank_sources failed: {str(e)[:200]}")}


async def verify_claims(report_markdown: str, sources: list[dict],
                        provider: str = "gemini", model: str = "gemini-2.5-flash") -> dict:
    """VERIFY skill — second-model verification. An independent model re-checks every cited claim
    in ``report_markdown`` against its ``sources``, rewrites contradicted claims, and flags weak
    ones. The provider key is read from the engine's encrypted vault (never passed here).

    Args:
        report_markdown: the report to verify (with [n] citation markers).
        sources: list of {"text": <source excerpt>} in citation order.
        provider: LLM provider id for the verifier model (default Gemini).
        model: model id for that provider.

    Returns:
        dict {"report_markdown", "contested", "flagged"} or {"error": ...}.
    """
    body = {"report_markdown": report_markdown, "sources": sources,
            "provider": provider, "model": model}
    try:
        async with httpx.AsyncClient(timeout=240, headers=_headers()) as c:
            r = await c.post(f"{API_URL}/api/verify", json=body)
            if r.status_code != 200:
                return {"error": f"verify failed ({r.status_code}): {r.text[:200]}"}
            return r.json()
    except Exception as e:
        return {"error": redact_keys(f"verify_claims failed: {str(e)[:200]}")}


# register the tools while keeping the originals plain-callable (for direct unit testing)
for _fn in (deep_research, get_report, rerank_sources, verify_claims):
    mcp.tool()(_fn)


def main():
    mcp.run()   # stdio transport — the ADK MCPToolset launches this via `python -m athena.mcp.server`


if __name__ == "__main__":
    main()
