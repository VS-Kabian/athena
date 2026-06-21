from athena.search.base import SearchHit, url_hash
from athena.search.merge import rrf_merge


def h(url, rank): return SearchHit(url=url, title=url, snippet="", rank=rank, provider="x")


def test_rrf_does_not_mutate_input_hits():
    a = h("https://a.com", 0)
    merged = rrf_merge([[a]], k=60)
    assert a.rrf_score == 0.0 and a.providers == []   # original input untouched
    assert merged[0].rrf_score != 0.0                 # the returned copy carries the score


def test_url_hash_canonicalizes_variants():
    base = url_hash("https://www.example.com/page")
    assert url_hash("http://example.com/page/") == base          # scheme + www + trailing slash
    assert url_hash("https://example.com/page?utm_source=x&ref=y") == base  # tracking params dropped
    assert url_hash("https://www.example.com/page#frag") == base  # fragment dropped
    assert url_hash("https://example.com/other") != base


def test_rrf_merges_and_dedups_by_url():
    a = [h("https://a.com", 0), h("https://b.com", 1)]
    b = [h("https://b.com/", 0), h("https://c.com", 1)]
    merged = rrf_merge([a, b], k=60)
    urls = [m.url for m in merged]
    assert urls[0].startswith("https://b.com")
    assert len([u for u in urls if "b.com" in u]) == 1


def test_rrf_score_formula():
    merged = rrf_merge([[h("https://a.com", 0)]], k=60)
    assert abs(merged[0].rrf_score - (1/60)) < 1e-9
