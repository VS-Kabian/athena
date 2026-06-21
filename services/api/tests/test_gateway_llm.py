import pytest
from unittest.mock import patch, AsyncMock
from athena.gateway.llm import complete

class FakeMsg: content = "hi"
class FakeChoice: message = FakeMsg()
class FakeResp: choices = [FakeChoice()]

@pytest.mark.asyncio
async def test_complete_routes_through_litellm():
    async def fake_acompletion(**kwargs):
        assert kwargs["model"] == "groq/llama-3.3-70b-versatile"
        return FakeResp()
    with patch("athena.gateway.llm.acompletion", side_effect=fake_acompletion):
        out = await complete("groq", "llama-3.3-70b-versatile", [{"role":"user","content":"yo"}], api_key="k")
        assert out == "hi"


@pytest.mark.asyncio
async def test_complete_retries_transient_error_then_succeeds():
    calls = {"n": 0}
    async def flaky(**kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("RateLimitError: 429 too many requests")
        return FakeResp()
    with patch("athena.gateway.llm.acompletion", side_effect=flaky), \
         patch("athena.gateway.llm.asyncio.sleep", AsyncMock()):
        out = await complete("groq", "llama-3.3-70b-versatile", [{"role":"user","content":"yo"}], api_key="k")
    assert out == "hi" and calls["n"] == 2          # retried once, then succeeded


@pytest.mark.asyncio
async def test_complete_does_not_retry_auth_error():
    calls = {"n": 0}
    async def bad_key(**kwargs):
        calls["n"] += 1
        raise RuntimeError("AuthenticationError: invalid api key (401)")
    with patch("athena.gateway.llm.acompletion", side_effect=bad_key), \
         patch("athena.gateway.llm.asyncio.sleep", AsyncMock()):
        with pytest.raises(RuntimeError):
            await complete("groq", "m", [{"role":"user","content":"yo"}], api_key="bad")
    assert calls["n"] == 1                            # auth failure fails fast, no retry
