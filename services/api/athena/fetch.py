import asyncio
import io
import ipaddress
import socket
from urllib.parse import urlparse

import httpx
import trafilatura

from . import cache
from .config import settings
from .log import get_logger

log = get_logger(__name__)
MIN_TEXT_LEN = 200   # below this, static extraction is considered "thin" and worth a JS retry


def _page_text(page) -> str:
    """One PDF page's text, preferring pypdf's LAYOUT mode — it preserves columns/tables (where benchmark
    numbers live) far better than the default flatten — and gracefully falling back to plain extraction
    when the installed pypdf is too old to support `extraction_mode` (P2-6). No new dependency."""
    try:
        t = page.extract_text(extraction_mode="layout")
        if t and t.strip():
            return t.strip()
    except Exception:
        pass
    try:
        return (page.extract_text() or "").strip()
    except Exception:
        return ""


def _extract_pdf(data: bytes, max_pages: int = 40) -> str | None:
    """Extract text from a PDF byte stream (pypdf, layout-aware). Returns None on any failure / no text —
    so a malformed or image-only PDF never crashes a fetch."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        parts = [t for page in reader.pages[:max_pages] if (t := _page_text(page))]
        return "\n\n".join(parts).strip() or None
    except Exception:
        return None


def _ip_is_public(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified)


def _is_safe_url(url: str) -> bool:
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False
        if p.username or p.password:
            return False   # reject embedded credentials (http://user:pass@internal/)
        host = p.hostname
        if not host:
            return False
        for info in socket.getaddrinfo(host, None):
            if not _ip_is_public(info[4][0]):
                return False
        return True
    except Exception:
        return False


def _peer_ip(r: httpx.Response) -> str | None:
    """The IP httpx actually connected to (best-effort). Used to defeat DNS-rebinding: the pre-flight
    _is_safe_url resolves DNS, but httpx re-resolves on connect — so we re-check the real peer."""
    try:
        stream = r.extensions.get("network_stream")
        addr = stream.get_extra_info("server_addr") if stream else None
        return addr[0] if addr else None
    except Exception:
        return None


async def render_js_html(url: str, timeout: float = 15.0) -> str | None:
    """Render a page in headless Chromium and return its HTML, or None if Playwright is
    unavailable or rendering fails. Used as a fallback for JS-heavy/SPA pages that yield no
    static text. SSRF note: the caller has already vetted `url`, but a headless browser also
    loads subresources — hence this path is gated behind the opt-in `settings.js_fetch` flag."""
    try:
        from playwright.async_api import async_playwright
    except Exception:
        return None
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            try:
                page = await browser.new_page(user_agent="ATHENA-Research/1.0")
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
                return await page.content()
            finally:
                await browser.close()
    except Exception:
        return None


async def fetch_extract(url: str, timeout: float = 8.0, max_bytes: int = 2_000_000) -> str | None:
    if not _is_safe_url(url):
        return None
    ck = cache.skey("fetch", url)
    cached = await cache.get_json(ck)
    if cached is not None:
        return cached or None
    try:
        # follow redirects MANUALLY and re-validate every hop — httpx's auto-follow would chase a
        # 302 to an internal/metadata IP (e.g. 169.254.169.254) without re-checking _is_safe_url.
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False,
                                     headers={"User-Agent": "ATHENA-Research/1.0"}) as c:
            cur = url
            data = b""
            ctype = ""
            for _ in range(5):
                if not _is_safe_url(cur):
                    return None
                # stream so we can stop reading at the byte cap instead of buffering a multi-GB body
                # into RAM; headers/status/redirect are available before we touch the body.
                async with c.stream("GET", cur) as r:
                    if r.is_redirect:
                        loc = r.headers.get("location")
                        if not loc:
                            return None
                        cur = str(r.url.join(loc))
                        continue
                    if r.status_code != 200:
                        return None
                    # TOCTOU guard: refuse if the connection actually landed on an internal IP (DNS
                    # rebinding between the _is_safe_url check and httpx's own resolution) BEFORE we
                    # consume any body bytes.
                    peer = _peer_ip(r)
                    if peer is None:
                        # guard couldn't read the connected IP (e.g. unusual transport) -> pre-flight
                        # DNS check is the only rebinding defense; make that observable.
                        log.debug("peer IP unavailable for %s; relying on pre-flight _is_safe_url only", cur)
                    elif not _ip_is_public(peer):
                        log.warning("fetch refused: %s connected to non-public peer %s", cur, peer)
                        return None
                    ctype = r.headers.get("content-type", "").lower()
                    is_pdf = "application/pdf" in ctype or cur.lower().split("?", 1)[0].endswith(".pdf")
                    cap = max_bytes * 6 if is_pdf else max_bytes   # PDFs run larger than HTML pages
                    buf = bytearray()
                    async for chunk in r.aiter_bytes():
                        buf.extend(chunk)
                        if len(buf) >= cap:
                            del buf[cap:]   # stop accumulating past the cap; abort the rest of the stream
                            break
                    data = bytes(buf)
                    break
            else:
                return None  # too many redirects
            is_pdf = "application/pdf" in ctype or cur.lower().split("?", 1)[0].endswith(".pdf")
            html = "" if is_pdf else data.decode("utf-8", errors="replace")
            data = data if is_pdf else b""
        if is_pdf:
            text = _extract_pdf(data)   # read the actual paper, not binary garbage
        else:
            text = trafilatura.extract(html, include_comments=False, include_tables=True)
            # JS fallback: static extraction came back empty/thin (likely a client-rendered SPA)
            if settings.js_fetch and (not text or len(text) < MIN_TEXT_LEN) and _is_safe_url(cur):
                rendered = await render_js_html(cur, timeout=max(timeout, 15.0))
                if rendered:
                    js_text = trafilatura.extract(rendered, include_comments=False, include_tables=True)
                    if js_text and len(js_text) > len(text or ""):
                        text = js_text
        # don't black-hole a transient/thin miss for a full day: cache real text for 24h, but an
        # empty extraction only briefly so a recovered page (or relaxed rate-limit) is retried soon.
        if text:
            await cache.set_json(ck, text, ttl=86400)
        else:
            await cache.set_json(ck, "", ttl=600)
        return text or None
    except Exception as e:
        log.debug("fetch failed for %s: %s", url, e)
        return None


async def fetch_html(url: str, timeout: float = 8.0, max_bytes: int = 2_000_000) -> str | None:
    """Fetch a page's raw HTML (SSRF-guarded, manual redirect re-validation + DNS-rebind peer check),
    for outbound-link harvesting in multi-hop chasing. Returns None on non-HTML (PDF/image/json) or any
    failure — only navigable HTML pages have links worth following."""
    if not _is_safe_url(url):
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=False,
                                     headers={"User-Agent": "ATHENA-Research/1.0"}) as c:
            cur = url
            for _ in range(5):
                if not _is_safe_url(cur):
                    return None
                async with c.stream("GET", cur) as r:
                    if r.is_redirect:
                        loc = r.headers.get("location")
                        if not loc:
                            return None
                        cur = str(r.url.join(loc))
                        continue
                    if r.status_code != 200:
                        return None
                    peer = _peer_ip(r)
                    if peer is not None and not _ip_is_public(peer):
                        return None
                    ctype = r.headers.get("content-type", "").lower()
                    if "pdf" in ctype or ctype.startswith("image/") or "json" in ctype:
                        return None
                    buf = bytearray()
                    async for chunk in r.aiter_bytes():
                        buf.extend(chunk)
                        if len(buf) >= max_bytes:
                            del buf[max_bytes:]
                            break
                    return bytes(buf).decode("utf-8", errors="replace")
            return None   # too many redirects
    except Exception as e:
        log.debug("fetch_html failed for %s: %s", url, e)
        return None


async def fetch_many(urls: list[str], limit: int = 12) -> dict[str, str]:
    sem = asyncio.Semaphore(6)

    async def one(u):
        async with sem:
            return u, await fetch_extract(u)

    results = await asyncio.gather(*[one(u) for u in urls[:limit]])
    return {u: t for u, t in results if t}
