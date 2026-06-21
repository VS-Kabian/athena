"""Cross-run long-term memory backed by pgvector.

At the end of a run we ``remember`` a short embedded summary; at the start of a new run we
``recall`` the most semantically similar prior runs to provide continuity / follow-up context.
Both are best-effort — callers wrap them so a memory failure never breaks a research run.
"""
import asyncio

from .db import execute, fetch
from .embed import embed_query, embed_passages


def _vec_literal(v) -> str:
    """pgvector text literal, e.g. '[0.1,0.2,...]', for ::vector casting via asyncpg."""
    return "[" + ",".join(f"{float(x):.6f}" for x in v) + "]"


def _summarize(topic: str, markdown: str, max_chars: int = 1200) -> str:
    body = (markdown or "").strip()
    if body.startswith("#"):              # drop the leading markdown H1 title line
        nl = body.find("\n")
        if nl != -1:
            body = body[nl + 1:].strip()
    return f"{topic} :: {body[:max_chars]}".strip()


async def remember(run_id: str, topic: str, markdown: str) -> None:
    summary = _summarize(topic, markdown)
    vecs = await asyncio.to_thread(embed_passages, [summary])   # embedding inference off the event loop
    if not vecs:
        return
    await execute(
        "insert into research_memory(run_id, topic, summary, embedding) values($1,$2,$3,$4::vector)",
        run_id, topic, summary, _vec_literal(vecs[0]))


async def recall(topic: str, k: int = 3, exclude_run_id: str | None = None,
                 min_similarity: float = 0.55) -> list[dict]:
    """Return up to ``k`` prior runs most similar to ``topic`` (cosine similarity, highest first).

    Only rows at or above ``min_similarity`` are returned, so genuinely unrelated prior runs
    don't surface as "related" just because the table is non-empty.
    """
    lit = _vec_literal(await asyncio.to_thread(embed_query, topic))
    if exclude_run_id:
        rows = await fetch(
            "select run_id, topic, summary, 1 - (embedding <=> $1::vector) as similarity "
            "from research_memory where embedding is not null and run_id <> $2::uuid "
            "and 1 - (embedding <=> $1::vector) >= $4 "
            "order by embedding <=> $1::vector limit $3", lit, exclude_run_id, k, min_similarity)
    else:
        rows = await fetch(
            "select run_id, topic, summary, 1 - (embedding <=> $1::vector) as similarity "
            "from research_memory where embedding is not null "
            "and 1 - (embedding <=> $1::vector) >= $3 "
            "order by embedding <=> $1::vector limit $2", lit, k, min_similarity)
    return [dict(r) for r in rows]
