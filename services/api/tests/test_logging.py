import logging
import pytest
from athena.search.registry import _safe


@pytest.mark.asyncio
async def test_provider_failure_is_logged_not_swallowed_silently(caplog):
    class BadProvider:
        name = "bad"
        async def search(self, q, k):
            raise RuntimeError("boom")

    with caplog.at_level(logging.WARNING):
        out = await _safe(BadProvider(), "q", 5)
    assert out == []                                          # still degrades gracefully
    assert any("bad" in r.message for r in caplog.records)    # ...but the failure is now visible
