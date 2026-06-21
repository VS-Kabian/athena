"""Agent-skill surface for the ATHENA engine.

The engine's two signature capabilities — cross-encoder **RERANK** (`embed.rerank`) and
second-model **VERIFY** (`agents.verifier.verify_report`) — are exposed here as small, discrete
HTTP endpoints. The MCP server (`athena.mcp.server`) wraps each as an MCP tool, so the Google ADK
agent can attach and call them as standalone *agent skills* — not only as steps buried inside a
full research run. Same hardened pipeline, now individually addressable.

Inputs are bounded (item counts + per-field length) so a caller can't exhaust memory/CPU, and the
CPU-bound reranker is offloaded to a worker thread so it can't block the event loop.
"""
import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from .auth import require_auth
from .keys import get_key
from ..embed import rerank as _rerank
from ..agents.verifier import verify_report
from ..gateway.registry import PROVIDERS

router = APIRouter(prefix="/api", tags=["skills"], dependencies=[Depends(require_auth)])

# Bounds — keep these endpoints from being a memory/CPU DoS primitive.
MAX_PASSAGES = 500
MAX_PASSAGE_CHARS = 20_000
MAX_SOURCES = 200
MAX_REPORT_CHARS = 200_000

_Passage = Annotated[str, StringConstraints(max_length=MAX_PASSAGE_CHARS)]


class RerankBody(BaseModel):
    query: Annotated[str, StringConstraints(max_length=4_000)]
    passages: list[_Passage] = Field(default_factory=list, max_length=MAX_PASSAGES)
    top_k: int | None = Field(default=None, ge=1, le=MAX_PASSAGES)


@router.post("/rerank")
async def rerank_skill(body: RerankBody):
    """Cross-encoder rerank: score each passage for relevance to ``query`` and return them
    sorted best-first. Falls back to input order (score 0.0) if the reranker is unavailable, so
    a caller always gets a usable ordering. The reranker runs in a worker thread (never blocks
    the event loop)."""
    passages = [p for p in body.passages if isinstance(p, str) and p.strip()]
    if not passages:
        return {"ranked": [], "count": 0}
    scores = await asyncio.to_thread(_rerank, body.query, passages)
    if not scores or len(scores) != len(passages):
        scores = [0.0] * len(passages)
    ranked = sorted(
        ({"index": i, "text": passages[i], "score": round(float(scores[i]), 4)}
         for i in range(len(passages))),
        key=lambda r: r["score"], reverse=True,
    )
    if body.top_k and body.top_k > 0:
        ranked = ranked[: body.top_k]
    return {"ranked": ranked, "count": len(ranked)}


class VerifySource(BaseModel):
    text: Annotated[str, StringConstraints(max_length=MAX_PASSAGE_CHARS)] = ""


class VerifyBody(BaseModel):
    report_markdown: Annotated[str, StringConstraints(max_length=MAX_REPORT_CHARS)]
    sources: list[VerifySource] = Field(default_factory=list, max_length=MAX_SOURCES)
    provider: str = "gemini"
    model: str = "gemini-2.5-flash"


@router.post("/verify")
async def verify_skill(body: VerifyBody):
    """Second-model verification: an independent model re-checks every cited claim against its
    source excerpt, rewriting contradicted claims and flagging weak ones. The provider key is read
    from the encrypted vault, so no key crosses the wire. Degrades gracefully (report unchanged)
    when no key is saved, so it can never break the calling agent."""
    if body.provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{body.provider}'")
    key = await get_key(body.provider)
    if not key and PROVIDERS[body.provider]["needs_key"]:
        return {"report_markdown": body.report_markdown, "contested": [], "flagged": 0,
                "note": f"no saved key for '{body.provider}' — verification skipped"}
    source_texts = [s.text or "" for s in body.sources]
    md, contested = await verify_report(
        body.report_markdown, source_texts,
        {"provider": body.provider, "model": body.model, "api_key": key},
    )
    return {"report_markdown": md, "contested": contested, "flagged": len(contested)}
