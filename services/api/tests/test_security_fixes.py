"""Regression tests for the security-audit fixes."""
import pytest
import respx
import httpx
from httpx import AsyncClient, ASGITransport

from athena.api.app import app


# ── SSRF: reject embedded credentials + non-http schemes (no network needed) ──
def test_is_safe_url_rejects_embedded_credentials():
    from athena.fetch import _is_safe_url
    assert _is_safe_url("http://user:pass@internal.host/") is False
    assert _is_safe_url("http://:secret@example.com/") is False


def test_is_safe_url_rejects_non_http_schemes():
    from athena.fetch import _is_safe_url
    assert _is_safe_url("file:///etc/passwd") is False
    assert _is_safe_url("gopher://example.com") is False


# ── Gemini provider key must travel in a header, never the URL query string ──
@pytest.mark.asyncio
@respx.mock
async def test_gemini_key_in_header_not_url():
    from athena.gateway.registry import list_models, PROVIDERS
    route = respx.get(PROVIDERS["gemini"]["models_url"]).mock(
        return_value=httpx.Response(200, json={"models": [{"name": "models/gemini-2.5-flash"}]}))
    await list_models("gemini", "SECRETKEY123")
    req = route.calls.last.request
    assert "SECRETKEY123" not in str(req.url)                 # key NOT in the URL
    assert req.headers.get("x-goog-api-key") == "SECRETKEY123"  # key in a header


# ── SSE stream must require the token (via ?token=) once one is configured ──
@pytest.mark.asyncio
async def test_stream_requires_token_when_configured(monkeypatch):
    from athena.config import settings
    monkeypatch.setattr(settings, "athena_api_token", "secret-tok")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        assert (await c.get("/api/research/abc/stream")).status_code == 401            # no token
        assert (await c.get("/api/research/abc/stream?token=wrong")).status_code == 401  # bad token
