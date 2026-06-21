from unittest.mock import patch
from athena.rag import chunk_text, build_evidence

def test_chunk_splits_long_text():
    chunks = chunk_text("word " * 1000, size=1200, overlap=150)
    assert len(chunks) >= 2

def test_build_evidence_ranks_and_caps_per_doc():
    docs = {"https://a.com": "alpha content here", "https://b.com": "beta content here"}
    with patch("athena.rag.embed_passages", side_effect=lambda t: [[1.0, 0.0] for _ in t]), \
         patch("athena.rag.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.rag.rerank", return_value=[]):  # fall back to embedding ranking
        ev = build_evidence("topic", docs, k=10, per_doc_cap=2)
    from collections import Counter
    counts = Counter(e["url"] for e in ev)
    assert len(ev) >= 1 and all(c <= 2 for c in counts.values())

def test_build_evidence_reserves_authoritative_sources():
    docs = {"https://arxiv.org/abs/1": "paper abstract about retrieval",
            "https://blog.com/a": "blog a content", "https://blog.com/b": "blog b content"}
    meta = {"https://arxiv.org/abs/1": {"trust": 0.75, "source_type": "paper"},
            "https://blog.com/a": {"trust": 0.45, "source_type": "blog"},
            "https://blog.com/b": {"trust": 0.45, "source_type": "blog"}}
    with patch("athena.rag.embed_passages", side_effect=lambda t: [[1.0, 0.0] for _ in t]), \
         patch("athena.rag.embed_query", return_value=[0.0, 1.0]), \
         patch("athena.rag.rerank", return_value=[]):
        ev = build_evidence("topic", docs, meta, k=10, per_doc_cap=2)
    assert "https://arxiv.org/abs/1" in {e["url"] for e in ev}

def test_build_evidence_uses_reranker_when_available():
    docs = {"https://a.com": "on topic content", "https://b.com": "off topic content"}
    with patch("athena.rag.embed_passages", side_effect=lambda t: [[1.0, 0.0] for _ in t]), \
         patch("athena.rag.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.rag.rerank", return_value=[9.0, -9.0]):  # a ranks far above b
        ev = build_evidence("topic", docs, k=10, per_doc_cap=2)
    assert ev[0]["url"] == "https://a.com"
