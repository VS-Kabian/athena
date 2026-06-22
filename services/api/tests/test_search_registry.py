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


class _Resp:
    def __init__(self, code, headers=None): self.status_code = code; self.headers = headers or {}

class _HTTPErr(Exception):
    def __init__(self, code, headers=None): self.response = _Resp(code, headers)


@pytest.mark.asyncio
async def test_safe_backs_off_on_429_honoring_retry_after():
    from athena.search import registry
    calls = {"n": 0}
    class RateLimited:
        name = "rl"
        async def search(self, q, k=10):
            calls["n"] += 1
            if calls["n"] == 1:
                raise _HTTPErr(429, {"Retry-After": "2"})
            return [SearchHit(url="https://ok.com", title="OK", snippet="", rank=0, provider="rl")]
    slept = []
    async def fake_sleep(s): slept.append(s)
    with patch("athena.search.registry.asyncio.sleep", side_effect=fake_sleep):
        out = await registry._safe(RateLimited(), "q", 5)
    assert [h.url for h in out] == ["https://ok.com"]   # recovered after honoring the backoff
    assert calls["n"] == 2 and slept and slept[0] == 2.0   # retried once, waited Retry-After (bounded)


@pytest.mark.asyncio
async def test_safe_does_not_retry_hard_4xx():
    from athena.search import registry
    calls = {"n": 0}
    class Forbidden:
        name = "fb"
        async def search(self, q, k=10):
            calls["n"] += 1
            raise _HTTPErr(404)
    with patch("athena.search.registry.asyncio.sleep", AsyncMock()):
        out = await registry._safe(Forbidden(), "q", 5)
    assert out == [] and calls["n"] == 1   # a 404 won't recover -> not retried


@pytest.mark.asyncio
async def test_retry_after_caps_a_hostile_value():
    from athena.search.registry import _retry_after_seconds
    assert _retry_after_seconds(_HTTPErr(429, {"Retry-After": "9999"})) == 5.0   # bounded
    assert _retry_after_seconds(_HTTPErr(503)) == 0.8                            # 5xx default backoff
    assert _retry_after_seconds(_HTTPErr(403)) == -1.0                           # hard client error
    assert _retry_after_seconds(RuntimeError("no response attr")) is None        # unknown -> default


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
