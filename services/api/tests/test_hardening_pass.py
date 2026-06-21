import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from athena.gateway.llm import redact_keys
from athena.api.events import EventBus
from athena.fetch import _is_safe_url

def test_redact_keys():
    # Test prefix-based keys
    assert redact_keys("error with sk-12345678901234567890") == "error with [REDACTED]"
    assert redact_keys("error with gsk-12345678901234567890") == "error with [REDACTED]"
    assert redact_keys("key AIzaSyD12345678901234567890") == "key [REDACTED]"
    
    # Test generic long alphanumeric keys (e.g. hex or random keys)
    assert redact_keys("abc123xyz123abc123xyz123abc123xyz123") == "[REDACTED]"  # 36 chars
    
    # Short things should remain untouched
    assert redact_keys("my-short-word") == "my-short-word"
    assert redact_keys("sk-short") == "sk-short"


@pytest.mark.asyncio
async def test_event_bus_cancelled_eviction():
    bus = EventBus()
    
    # 1. Test terminal event cleanup
    bus.cancel("run-1")
    assert bus.is_cancelled("run-1") is True
    
    await bus.publish("run-1", {"type": "done", "data": {}})
    assert bus.is_cancelled("run-1") is False

    # 2. Test FIFO backlog eviction cleanup
    # We will temporarily mock _MAX_RUNS to a small value
    with patch("athena.api.events._MAX_RUNS", 2):
        bus.cancel("run-A")
        bus.cancel("run-B")
        bus.cancel("run-C")
        
        # Publish to run-A, run-B, run-C to trigger eviction of A
        await bus.publish("run-A", {"type": "progress", "data": {}})
        await bus.publish("run-B", {"type": "progress", "data": {}})
        await bus.publish("run-C", {"type": "progress", "data": {}})
        
        # run-A should be evicted from self._cancelled
        assert bus.is_cancelled("run-A") is False
        assert bus.is_cancelled("run-B") is True
        assert bus.is_cancelled("run-C") is True


@pytest.mark.asyncio
async def test_unsafe_search_url_filtering():
    # Verify that unsafe URLs are correctly classified as unsafe
    assert _is_safe_url("javascript:alert(1)") is False
    assert _is_safe_url("data:text/html,x") is False
    assert _is_safe_url("file:///etc/passwd") is False
    assert _is_safe_url("http://user:pass@internal.host/") is False
    assert _is_safe_url("https://google.com") is True
