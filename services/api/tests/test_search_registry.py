import pytest
from unittest.mock import patch, AsyncMock
from athena.search.base import SearchHit
from athena.search.registry import multi_search


@pytest.fixture(autouse=True)
def _no_cache():
    # default: cache miss + no-op set, so existing tests exercise the providers directly
    with patch("athena.search.registry.cache.get_json", return_value=None), \
         patch("athena.search.registry.cache.set_json", return_value=None):
        yield


class Fake:
    def __init__(self, name, urls, fail=False): self.name=name; self.urls=urls; self.fail=fail
    async def search(self, q, k=10):
        if self.fail: raise RuntimeError("down")
        return [SearchHit(url=u, title=u, snippet="", rank=i, provider=self.name) for i,u in enumerate(self.urls)]


@pytest.mark.asyncio
async def test_broadcast_merges_all():
    res = await multi_search("q", [Fake("a",["https://x.com"]), Fake("b",["https://y.com"])], mode="broadcast")
    assert {h.url for h in res} == {"https://x.com","https://y.com"}


@pytest.mark.asyncio
async def test_broadcast_survives_one_provider_down():
    res = await multi_search("q", [Fake("a",["https://x.com"]), Fake("b",[],fail=True)], mode="broadcast")
    assert {h.url for h in res} == {"https://x.com"}


@pytest.mark.asyncio
async def test_single_uses_first_only():
    res = await multi_search("q", [Fake("a",["https://x.com"]), Fake("b",["https://y.com"])], mode="single")
    assert {h.url for h in res} == {"https://x.com"}


@pytest.mark.asyncio
async def test_provider_transient_error_is_retried_once():
    calls = {"n": 0}
    class Flaky:
        name = "f"
        async def search(self, q, k=10):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("temporary blip")
            return [SearchHit(url="https://ok.com", title="OK", snippet="", rank=0, provider="f")]
    with patch("athena.search.registry.asyncio.sleep", AsyncMock()):
        res = await multi_search("q", [Flaky()], mode="single")
    assert calls["n"] == 2 and {h.url for h in res} == {"https://ok.com"}   # retried, then succeeded


@pytest.mark.asyncio
async def test_empty_results_negative_cached_briefly_not_for_a_day():
    captured = []
    async def cap_set(k, v, ttl=86400): captured.append((v, ttl))
    class Empty:
        name = "e"
        async def search(self, q, k=10): return []
    with patch("athena.search.registry.cache.get_json", AsyncMock(return_value=None)), \
         patch("athena.search.registry.cache.set_json", side_effect=cap_set):
        res = await multi_search("q", [Empty()], mode="single")
    assert res == []
    assert captured and captured[-1][1] == 600   # empty result cached briefly, not 24h


@pytest.mark.asyncio
async def test_multi_search_uses_cache_on_hit():
    calls = {"n": 0}
    class Counting:
        name = "c"
        async def search(self, q, k=10):
            calls["n"] += 1
            return [SearchHit(url="https://x.com", title="X", snippet="", rank=0, provider="c")]
    cached_payload = [{"url": "https://cached.com", "title": "C", "snippet": "", "rank": 0,
                       "provider": "c", "rrf_score": 0.0, "providers": [], "relevance": 0.0}]
    with patch("athena.search.registry.cache.get_json", return_value=cached_payload), \
         patch("athena.search.registry.cache.set_json", return_value=None):
        res = await multi_search("q", [Counting()], mode="broadcast")
    assert calls["n"] == 0  # provider NOT called — served from cache
    assert res[0].url == "https://cached.com"
