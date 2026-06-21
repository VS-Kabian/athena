from unittest.mock import patch
from athena.search.base import SearchHit
from athena.search.relevance import filter_by_relevance


def mk(url, title, snippet="s"):
    return SearchHit(url=url, title=title, snippet=snippet, rank=0, provider="ddg")


def test_drops_low_relevance_spam_via_reranker():
    hits = [mk("https://a.com", "RAG frameworks"), mk("https://spam.com", "Hire PHP Developers")]

    def fake_rerank(q, passages):
        return [6.0 if "RAG" in p else -6.0 for p in passages]

    with patch("athena.search.relevance.rerank", side_effect=fake_rerank):
        out = filter_by_relevance("RAG frameworks", hits, threshold=0.5)
    urls = [h.url for h in out]
    assert "https://a.com" in urls and "https://spam.com" not in urls
    assert out[0].relevance > 0.9  # sigmoid(6.0) ~ 0.998


def _topical():
    return [mk("https://a.com/on", "On-topic transformers attention", "self-attention nlp"),
            mk("https://b.com/off", "Cooking pasta recipes", "boil water add salt")]


def test_rerank_keeps_on_topic_and_relevance_in_unit_range():
    def fake_rerank(q, passages):
        return [5.0 if ("attention" in p or "self-attention" in p) else -5.0 for p in passages]

    with patch("athena.search.relevance.rerank", side_effect=fake_rerank):
        kept = filter_by_relevance("how transformers attention works", _topical())
    assert [h.url for h in kept] == ["https://a.com/on"]
    assert all(0.0 <= h.relevance <= 1.0 for h in kept)


def test_falls_back_to_cosine_when_reranker_unavailable():
    with patch("athena.search.relevance.rerank", return_value=[]), \
         patch("athena.search.relevance.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.search.relevance.embed_passages", return_value=[[1.0, 0.0], [0.0, 1.0]]):
        kept = filter_by_relevance("transformers attention", _topical())
    assert [h.url for h in kept] == ["https://a.com/on"]  # cosine path, threshold 0.60
    assert all(0.0 <= h.relevance <= 1.0 for h in kept)


def test_min_keep_floor_prevents_empty_result():
    hits = [mk("https://a.com", "x"), mk("https://b.com", "y"), mk("https://c.com", "z")]

    def fake_rerank(q, passages):
        return [-3.0, -2.0, -1.0]  # every sigmoid < 0.5 -> would be empty without the floor

    with patch("athena.search.relevance.rerank", side_effect=fake_rerank):
        kept = filter_by_relevance("q", hits)
    assert len(kept) >= 1                       # never starved to empty
    assert kept[0].url == "https://c.com"       # best score (-1.0) first
