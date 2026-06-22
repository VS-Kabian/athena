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
    assert len(kept) >= 1                       # never starved to empty (best score 0.27 clears the floor)
    assert kept[0].url == "https://c.com"       # best score (-1.0) first


def test_min_keep_floor_drops_wholly_offtopic_batch():
    # P3: when EVERY candidate is far below relevance, return nothing rather than force-feeding junk
    hits = [mk("https://a.com", "x"), mk("https://b.com", "y")]

    def fake_rerank(q, passages):
        return [-8.0, -7.0]                     # sigmoids ~0.0003 / 0.0009 -> below the absolute floor

    with patch("athena.search.relevance.rerank", side_effect=fake_rerank):
        kept = filter_by_relevance("q", hits)
    assert kept == []                           # wholly off-topic batch -> no junk forced into the pipeline


# ── P1-3: content-aware re-ranking on fetched page bodies ──
def test_content_relevance_rescores_on_body_and_returns_unit_scores():
    from athena.search import relevance
    relevance._SCORE_CACHE.clear()
    with patch("athena.search.relevance.rerank", return_value=[6.0, -6.0]):
        scores = relevance.content_relevance("langgraph", ["LangGraph runtime body", "unrelated cooking body"])
    assert scores is not None and len(scores) == 2
    assert all(0.0 <= s <= 1.0 for s in scores)
    assert scores[0] > 0.9 and scores[1] < 0.1   # sigmoid-shaped, on-topic body ranked far above off-topic


def test_content_relevance_none_when_reranker_unavailable():
    from athena.search import relevance
    relevance._SCORE_CACHE.clear()
    with patch("athena.search.relevance.rerank", return_value=[]):   # reranker down -> caller keeps prior relevance
        assert relevance.content_relevance("topic", ["some fetched body text"]) is None


def test_content_relevance_empty_input_returns_empty():
    from athena.search import relevance
    assert relevance.content_relevance("topic", []) == []


def test_content_relevance_truncates_long_body():
    from athena.search import relevance
    relevance._SCORE_CACHE.clear()
    seen = {}

    def spy(q, passages):
        seen["len"] = len(passages[0])
        return [3.0]

    with patch("athena.search.relevance.rerank", side_effect=spy):
        relevance.content_relevance("topic", ["B" * 9000])
    assert seen["len"] <= relevance._CONTENT_MAX   # body trimmed before the cross-encoder
