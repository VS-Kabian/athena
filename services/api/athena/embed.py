import numpy as np

_model = None
_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

def _get_model():
    global _model
    if _model is None:
        from fastembed import TextEmbedding
        _model = TextEmbedding("BAAI/bge-small-en-v1.5")
    return _model

def embed_passages(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return [list(map(float, v)) for v in _get_model().embed(list(texts))]

def embed_query(text: str) -> list[float]:
    return list(map(float, list(_get_model().embed([_QUERY_PREFIX + text]))[0]))

def cosine(a, b) -> float:
    a = np.asarray(a, dtype=float); b = np.asarray(b, dtype=float)
    na = float(np.linalg.norm(a)); nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))

def top_k(query_vec, items, key, k):
    return sorted(items, key=lambda it: cosine(query_vec, key(it)), reverse=True)[:k]

_reranker = None

def _get_reranker():
    global _reranker
    if _reranker is None:
        from fastembed.rerank.cross_encoder import TextCrossEncoder
        _reranker = TextCrossEncoder("Xenova/ms-marco-MiniLM-L-6-v2")
    return _reranker

def rerank(query: str, passages: list[str]) -> list[float]:
    """Cross-encoder relevance scores (logits) for (query, passage) pairs. Sharper than cosine.
    Returns [] on any failure so callers can fall back gracefully."""
    if not passages:
        return []
    try:
        return [float(s) for s in _get_reranker().rerank(query, passages)]
    except Exception:
        return []
