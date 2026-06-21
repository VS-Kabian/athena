import pytest, respx, httpx
from unittest.mock import patch, AsyncMock
from athena.fetch import _is_safe_url, fetch_extract


@pytest.fixture(autouse=True)
def _no_cache():
    with patch("athena.fetch.cache.get_json", return_value=None), \
         patch("athena.fetch.cache.set_json", return_value=None):
        yield


def test_blocks_non_http_schemes():
    assert not _is_safe_url("file:///etc/passwd")
    assert not _is_safe_url("ftp://x")

def test_blocks_private_and_loopback_ips():
    assert not _is_safe_url("http://127.0.0.1/x")
    assert not _is_safe_url("http://10.0.0.5/x")
    assert not _is_safe_url("http://169.254.1.1/")
    assert not _is_safe_url("http://192.168.1.1/")

def test_allows_public_host_when_resolves_public():
    with patch("athena.fetch.socket.getaddrinfo",
               return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
        assert _is_safe_url("https://example.com/page")

@pytest.mark.asyncio
@respx.mock
async def test_fetch_extract_returns_main_text():
    html = "<html><body><article><h1>RAG</h1><p>" + ("Retrieval augmented generation is useful. " * 8) + "</p></article></body></html>"
    respx.get("https://example.com/a").mock(return_value=httpx.Response(200, text=html))
    with patch("athena.fetch.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
        text = await fetch_extract("https://example.com/a")
    assert text and "Retrieval augmented generation" in text


_SPA_HTML = "<html><body><div id='root'></div></body></html>"  # client-rendered: no static text
_RENDERED = ("<html><body><article><p>" + ("Rendered SPA content sentence. " * 8)
             + "</p></article></body></html>")


@pytest.mark.asyncio
@respx.mock
async def test_js_fallback_recovers_empty_extraction_when_enabled():
    respx.get("https://spa.example.com/app").mock(return_value=httpx.Response(200, text=_SPA_HTML))
    with patch("athena.fetch.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]), \
         patch("athena.fetch.settings.js_fetch", True), \
         patch("athena.fetch.render_js_html", AsyncMock(return_value=_RENDERED)) as render:
        text = await fetch_extract("https://spa.example.com/app")
    render.assert_awaited_once()
    assert text and "Rendered SPA content" in text


@pytest.mark.asyncio
@respx.mock
async def test_no_js_fallback_when_disabled():
    respx.get("https://spa.example.com/app2").mock(return_value=httpx.Response(200, text=_SPA_HTML))
    render = AsyncMock(return_value=_RENDERED)
    with patch("athena.fetch.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]), \
         patch("athena.fetch.settings.js_fetch", False), \
         patch("athena.fetch.render_js_html", render):
        text = await fetch_extract("https://spa.example.com/app2")
    render.assert_not_called()
    assert text is None  # thin SPA, fallback off -> nothing extracted


@pytest.mark.asyncio
@respx.mock
async def test_js_fallback_skipped_when_static_extraction_is_rich():
    html = "<html><body><article><h1>Doc</h1><p>" + ("Plenty of real static text here. " * 12) + "</p></article></body></html>"
    respx.get("https://rich.example.com/p").mock(return_value=httpx.Response(200, text=html))
    render = AsyncMock(return_value=_RENDERED)
    with patch("athena.fetch.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]), \
         patch("athena.fetch.settings.js_fetch", True), \
         patch("athena.fetch.render_js_html", render):
        text = await fetch_extract("https://rich.example.com/p")
    render.assert_not_called()  # static text already above MIN_TEXT_LEN -> no browser needed
    assert text and "Plenty of real static text" in text


import ipaddress as _ipaddr


def _gai(host, *a, **k):
    # literal IPs resolve to themselves (so link-local stays link-local); domains resolve public
    try:
        _ipaddr.ip_address(host)
        return [(2, 1, 6, "", (host, 0))]
    except ValueError:
        return [(2, 1, 6, "", ("93.184.216.34", 0))]


@pytest.mark.asyncio
@respx.mock
async def test_blocks_redirect_to_internal_metadata_ip():
    respx.get("https://evil.example.com/start").mock(
        return_value=httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"}))
    with patch("athena.fetch.socket.getaddrinfo", side_effect=_gai):
        text = await fetch_extract("https://evil.example.com/start")
    assert text is None   # redirect to cloud-metadata IP is re-validated and rejected


@pytest.mark.asyncio
@respx.mock
async def test_follows_safe_redirect():
    respx.get("https://example.com/a").mock(
        return_value=httpx.Response(301, headers={"location": "https://example.com/b"}))
    html = "<html><body><article><p>" + ("Good content here. " * 10) + "</p></article></body></html>"
    respx.get("https://example.com/b").mock(return_value=httpx.Response(200, text=html))
    with patch("athena.fetch.socket.getaddrinfo", side_effect=_gai):
        text = await fetch_extract("https://example.com/a")
    assert text and "Good content" in text


@pytest.mark.asyncio
@respx.mock
async def test_fetch_extracts_pdf_via_pypdf():
    respx.get("https://example.com/paper.pdf").mock(
        return_value=httpx.Response(200, content=b"%PDF-1.4 fake bytes",
                                    headers={"content-type": "application/pdf"}))
    with patch("athena.fetch.socket.getaddrinfo", side_effect=_gai), \
         patch("athena.fetch._extract_pdf", return_value="EXTRACTED PAPER TEXT") as ex:
        text = await fetch_extract("https://example.com/paper.pdf")
    ex.assert_called_once()                      # routed to the PDF path, not trafilatura
    assert text == "EXTRACTED PAPER TEXT"


def test_extract_pdf_returns_none_on_garbage():
    from athena.fetch import _extract_pdf
    assert _extract_pdf(b"not a real pdf") is None   # never raises on malformed input


@pytest.mark.asyncio
async def test_fetch_extract_returns_cached_text():
    with patch("athena.fetch.cache.get_json", return_value="CACHED PAGE TEXT"), \
         patch("athena.fetch.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
        text = await fetch_extract("https://example.com/x")
    assert text == "CACHED PAGE TEXT"  # served from cache, no network


@pytest.mark.asyncio
@respx.mock
async def test_rejects_dns_rebinding_via_connected_peer_ip():
    class _Stream:
        def get_extra_info(self, k):
            return ("169.254.169.254", 443) if k == "server_addr" else None
    html = "<html><body><article><p>" + ("metadata secret leak. " * 10) + "</p></article></body></html>"
    respx.get("https://rebind.example.com/x").mock(
        return_value=httpx.Response(200, text=html, extensions={"network_stream": _Stream()}))
    # pre-flight DNS resolves public (passes _is_safe_url), but the real connected peer is link-local
    with patch("athena.fetch.socket.getaddrinfo", return_value=[(2, 1, 6, "", ("93.184.216.34", 0))]):
        text = await fetch_extract("https://rebind.example.com/x")
    assert text is None   # refused at the peer-IP check before the body is parsed


@pytest.mark.asyncio
@respx.mock
async def test_empty_extraction_cached_briefly_not_for_a_day():
    captured = []
    async def cap_set(k, v, ttl=86400): captured.append((v, ttl))
    respx.get("https://thin.example.com/p").mock(return_value=httpx.Response(200, text="<html><body></body></html>"))
    with patch("athena.fetch.socket.getaddrinfo", side_effect=_gai), \
         patch("athena.fetch.cache.get_json", AsyncMock(return_value=None)), \
         patch("athena.fetch.cache.set_json", side_effect=cap_set), \
         patch("athena.fetch.settings.js_fetch", False):
        text = await fetch_extract("https://thin.example.com/p")
    assert text is None
    assert captured and captured[-1] == ("", 600)   # transient/thin miss cached only briefly, not 24h


@pytest.mark.asyncio
@respx.mock
async def test_rich_extraction_cached_for_a_day():
    captured = []
    async def cap_set(k, v, ttl=86400): captured.append((v, ttl))
    html = "<html><body><article><p>" + ("Solid real content here. " * 12) + "</p></article></body></html>"
    respx.get("https://rich.example.com/q").mock(return_value=httpx.Response(200, text=html))
    with patch("athena.fetch.socket.getaddrinfo", side_effect=_gai), \
         patch("athena.fetch.cache.get_json", AsyncMock(return_value=None)), \
         patch("athena.fetch.cache.set_json", side_effect=cap_set), \
         patch("athena.fetch.settings.js_fetch", False):
        text = await fetch_extract("https://rich.example.com/q")
    assert text and "Solid real content" in text
    assert captured and captured[-1][1] == 86400     # real text still cached for the full day
