import re

from .embed import embed_query, embed_passages, cosine, rerank

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str, max_len: int = 400) -> list[str]:
    """Split text into sentence-ish spans. Over-long 'sentences' are windowed so a single
    run-on paragraph can't swallow the whole span."""
    text = " ".join((text or "").split())
    if not text:
        return []
    out: list[str] = []
    for s in _SENT_SPLIT.split(text):
        s = s.strip()
        if not s:
            continue
        if len(s) > max_len:
            out.extend(s[i:i + max_len] for i in range(0, len(s), max_len))
        else:
            out.append(s)
    return out


def select_span(query: str, text: str, max_chars: int = 400) -> str:
    """Return the single most query-relevant sentence/span from ``text`` (span-level citation).

    Cross-encoder rerank picks the best sentence; falls back to embedding similarity, and
    finally to the leading text — so callers always get a usable excerpt and never raise.
    """
    text = (text or "").strip()
    if not text:
        return ""
    sents = split_sentences(text)
    if len(sents) <= 1:
        return text[:max_chars]
    try:
        scores = rerank(query, sents)
        if scores and len(scores) == len(sents):
            best = max(range(len(sents)), key=lambda i: scores[i])
            return sents[best][:max_chars]
    except Exception:
        pass
    try:
        qv = embed_query(query)
        vecs = embed_passages(sents)
        if vecs and len(vecs) == len(sents):   # mirror the rerank branch's length guard
            best = max(range(len(sents)), key=lambda i: cosine(qv, vecs[i]))
            return sents[best][:max_chars]
    except Exception:
        pass
    return text[:max_chars]


def chunk_text(text: str, size: int = 1200, overlap: int = 150) -> list[str]:
    text = " ".join((text or "").split())
    if not text:
        return []
    chunks, i = [], 0
    step = max(size - overlap, 1)
    while i < len(text):
        chunks.append(text[i:i + size])
        i += step
    return chunks


def build_evidence(topic: str, docs: dict[str, str], meta: dict | None = None,
                   k: int = 32, per_doc_cap: int = 3) -> list[dict]:
    """Rank source chunks for the report.

    1) embed-rank all chunks (fast), 2) cross-encoder RERANK the top candidates for sharp
    precision (off-topic chunks score strongly negative and drop out), 3) reserve the best
    chunk of up to 2 sources per authoritative type (paper/github/docs), 4) fill by score.
    Falls back to embedding-only ranking if the reranker is unavailable.
    `meta`: {url: {"trust": float, "source_type": str}}.
    """
    meta = meta or {}
    items = []
    for url, text in docs.items():
        chs = chunk_text(text)[:8]
        if not chs:
            continue
        vecs = embed_passages(chs)
        info = meta.get(url, {})
        trust = float(info.get("trust", 0.5))
        stype = info.get("source_type", "web")
        for ch, v in zip(chs, vecs):
            items.append({"url": url, "text": ch, "vec": v, "trust": trust, "stype": stype})
    if not items:
        return []

    qv = embed_query(topic)
    for it in items:
        it["emb"] = cosine(qv, it["vec"])
    items.sort(key=lambda x: x["emb"], reverse=True)

    # cross-encoder rerank the top embedding candidates
    cand = items[:48]
    rr = rerank(topic, [it["text"] for it in cand])
    if rr and len(rr) == len(cand):
        for it, s in zip(cand, rr):
            it["score"] = round(s + 0.4 * it["trust"], 4)   # reranker dominates; small trust nudge
        cand.sort(key=lambda x: x["score"], reverse=True)
        pool = cand
        # the reranked candidates are the precise top; the rest keep their embedding score so the
        # FILL loop can still reach `k` from items ranked 49+ when a few URLs dominate the top-48.
        cand_ids = {id(it) for it in cand}
        for it in items:
            if id(it) not in cand_ids:
                it["score"] = round(it["emb"] * (1.0 + 0.4 * it["trust"]), 4)
        fill_pool = cand + [it for it in items if id(it) not in cand_ids]
    else:
        for it in items:
            it["score"] = round(it["emb"] * (1.0 + 0.4 * it["trust"]), 4)
        pool = items
        fill_pool = items

    out, seen = [], {}

    def _add(it):
        out.append({"url": it["url"], "text": it["text"], "score": it.get("score", 0.0)})
        seen[it["url"]] = seen.get(it["url"], 0) + 1

    # reserve the best chunk of authoritative types from the sharply-reranked candidates
    for stype in ("paper", "github", "docs"):
        done = set()
        for it in pool:
            if it["stype"] != stype or it["url"] in seen or it["url"] in done:
                continue
            _add(it)
            done.add(it["url"])
            if len(done) >= 2:
                break

    # fill by score, drawing from the FULL item list (not just top-48) so `k` is reachable
    for it in fill_pool:
        if len(out) >= k:
            break
        if seen.get(it["url"], 0) >= per_doc_cap:
            continue
        _add(it)

    return out[:k]
