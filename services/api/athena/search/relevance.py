import math

from .base import SearchHit
from ..embed import embed_query, embed_passages, cosine, rerank


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


# Memoize cross-encoder scores by (query, passage-text). The same (topic, title+snippet) pair is
# re-scored across overlapping sub-questions/rounds; rerank is deterministic so caching is safe.
# Bounded so the table can't grow unboundedly during a long run; clear wholesale on overflow.
_SCORE_CACHE: dict[tuple[str, str], float] = {}
_SCORE_CACHE_CAP = 5000


def _rerank_cached(topic: str, texts: list[str]) -> list[float]:
    """rerank(topic, texts) with per-(query,text) memoization. Returns [] (like rerank) when the
    reranker can't score the *uncached* texts, so callers keep their cosine-fallback behavior."""
    # Bound the cache BEFORE this call's bookkeeping. Clearing mid-call (after `todo` is computed)
    # would drop entries for texts already cached from a prior call that are NOT in `todo`, making
    # the final lookup KeyError. Clearing up-front means `todo` is recomputed against the cleared
    # cache, so every text this call needs gets (re)scored and is present at return time.
    if len(_SCORE_CACHE) > _SCORE_CACHE_CAP:
        _SCORE_CACHE.clear()
    todo = [t for t in texts if (topic, t) not in _SCORE_CACHE]
    if todo:
        # rerank only the texts we haven't scored yet; dedupe to avoid re-scoring repeats in one call
        uniq = list(dict.fromkeys(todo))
        fresh = rerank(topic, uniq)
        if not fresh or len(fresh) != len(uniq):
            return []   # reranker unavailable/mismatched -> signal fallback (don't poison the cache)
        for t, s in zip(uniq, fresh):
            _SCORE_CACHE[(topic, t)] = s
    return [_SCORE_CACHE[(topic, t)] for t in texts]


def filter_by_relevance(topic: str, hits: list[SearchHit], threshold: float = 0.50,
                        min_keep: int = 5) -> list[SearchHit]:
    """Keep hits relevant to ``topic``. Primary path uses the cross-encoder reranker (sharper than
    cosine on short snippets); ``h.relevance`` is the sigmoid of the rerank score so it stays in
    [0, 1] for downstream scoring. Falls back to embedding cosine when the reranker is unavailable.

    If the threshold would drop *everything* (a miscalibrated batch), keep the top ``min_keep`` by
    score instead — never starve the pipeline of all sources.
    """
    if not hits:
        return []
    texts = [f"{h.title}. {h.snippet}" for h in hits]
    scores = _rerank_cached(topic, texts)
    if scores and len(scores) == len(hits):
        scored = [(h, round(_sigmoid(s), 3)) for h, s in zip(hits, scores)]
    else:
        # fallback: embedding cosine (original behaviour) when the reranker can't score
        qv = embed_query(topic)
        vecs = embed_passages(texts)
        threshold = 0.60
        scored = [(h, round(cosine(qv, v), 3)) for h, v in zip(hits, vecs)]
    for h, r in scored:
        h.relevance = r
    kept = [h for h, r in scored if r >= threshold]
    if not kept:
        kept = [h for h, _ in sorted(scored, key=lambda x: x[1], reverse=True)[:min_keep]]
    return kept
