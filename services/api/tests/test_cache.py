import pytest
from unittest.mock import patch
from athena import cache

@pytest.mark.asyncio
async def test_cache_roundtrip():
    store = {}
    class FakeR:
        async def get(self, k): return store.get(k)
        async def set(self, k, v, ex=None): store[k] = v
    with patch("athena.cache._r", return_value=FakeR()):
        await cache.set_json("k1", {"a": 1})
        assert await cache.get_json("k1") == {"a": 1}
        assert await cache.get_json("missing") is None

@pytest.mark.asyncio
async def test_cache_graceful_when_down():
    def boom(): raise RuntimeError("redis down")
    with patch("athena.cache._r", side_effect=boom):
        assert await cache.get_json("k") is None
        await cache.set_json("k", {"a": 1})  # must not raise

def test_skey_stable_and_distinct():
    assert cache.skey("p", "a", "b") == cache.skey("p", "a", "b")
    assert cache.skey("p", "a") != cache.skey("p", "b")
