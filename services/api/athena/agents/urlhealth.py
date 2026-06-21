"""URL liveness / fabrication detection — the cheapest trust-moat win (#4).

Studies of frontier deep-research systems find 3–13% of citation URLs are fabricated and 5–18% don't
resolve — and almost no system checks. This module HEAD/GET-probes every cited source URL, behind the
same SSRF guards as ``fetch`` (manual redirect re-validation + DNS-rebinding peer check), and labels
each LIVE / DEAD / UNREACHABLE so the report can badge dead links instead of citing them blindly.

LIVE     — the URL resolves to a real page (2xx/3xx, or a gated 401/403/429 — it exists).
DEAD     — the page is gone (404/410 or other 4xx): a strong "fabricated / stale citation" signal.
UNREACHABLE — server error (5xx) or DNS/connection failure: ambiguous (transient OR fabricated host).
"""
import asyncio

import httpx

from .. import cache
from ..fetch import _ip_is_public, _is_safe_url, _peer_ip
from ..log import get_logger

log = get_logger(__name__)

LIVE, DEAD, UNREACHABLE = "live", "dead", "unreachable"
_MAX_URLS = 40        # bound the probe fan-out per report
_CONCURRENCY = 8
_TIMEOUT = 6.0
_GATED = (401, 403, 429)   # the server answered: the page exists, it's just access-controlled


def _classify(code: int | None) -> str:
    if code is None:
        return UNREACHABLE
    if 200 <= code < 400 or code in _GATED:
        return LIVE
    if 400 <= code < 500:
        return DEAD          # 404/410/etc — page not found / gone
    return UNREACHABLE       # 5xx — server-side error, treat as transient/ambiguous


async def _probe(url: str, client: httpx.AsyncClient) -> dict:
    """One SSRF-guarded liveness probe with manual redirect following (max 5 hops)."""
    cur = url
    for _ in range(5):
        if not _is_safe_url(cur):
            return {"status": UNREACHABLE, "code": None, "reason": "blocked"}
        try:
            async with client.stream("GET", cur) as r:
                if r.is_redirect:
                    loc = r.headers.get("location")
                    if not loc:
                        return {"status": DEAD, "code": r.status_code}
                    cur = str(r.url.join(loc))
                    continue
                peer = _peer_ip(r)
                if peer is not None and not _ip_is_public(peer):
                    return {"status": UNREACHABLE, "code": None, "reason": "blocked"}
                return {"status": _classify(r.status_code), "code": r.status_code}
        except Exception as e:
            log.debug("urlhealth probe failed for %s: %s", cur, e)
            return {"status": UNREACHABLE, "code": None, "reason": "error"}
    return {"status": DEAD, "code": None, "reason": "too_many_redirects"}


async def _check_one(url: str, client: httpx.AsyncClient, sem: asyncio.Semaphore) -> tuple[str, dict]:
    ck = cache.skey("urlhealth", url)
    cached = await cache.get_json(ck)
    if cached is not None:
        return url, cached
    if not _is_safe_url(url):
        res = {"status": UNREACHABLE, "code": None, "reason": "blocked"}
    else:
        async with sem:
            res = await _probe(url, client)
    # cache resolved verdicts for a day; recheck ambiguous/unreachable soon (could be transient)
    await cache.set_json(ck, res, ttl=86400 if res["status"] in (LIVE, DEAD) else 600)
    return url, res


async def check_urls(urls: list[str]) -> dict[str, dict]:
    """Probe each unique URL once. Returns {url: {"status","code"[,"reason"]}}. Never raises —
    a probe failure becomes an UNREACHABLE verdict so the caller can finish the report regardless."""
    seen: list[str] = []
    for u in urls:
        if u and u not in seen:
            seen.append(u)
    seen = seen[:_MAX_URLS]
    if not seen:
        return {}
    sem = asyncio.Semaphore(_CONCURRENCY)
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=False,
                                     headers={"User-Agent": "ATHENA-Research/1.0"}) as client:
            pairs = await asyncio.gather(*[_check_one(u, client, sem) for u in seen],
                                         return_exceptions=True)
    except Exception as e:
        log.warning("urlhealth batch failed: %s", e)
        return {}
    out: dict[str, dict] = {}
    for p in pairs:
        if isinstance(p, Exception):
            continue
        url, res = p
        out[url] = res
    return out


def summarize(results: dict[str, dict]) -> dict:
    """Counts + the list of dead/unreachable URLs for the report's flagged list."""
    live = sum(1 for r in results.values() if r["status"] == LIVE)
    dead = sum(1 for r in results.values() if r["status"] == DEAD)
    unreachable = sum(1 for r in results.values() if r["status"] == UNREACHABLE)
    bad = [u for u, r in results.items() if r["status"] != LIVE]
    return {"total": len(results), "live": live, "dead": dead, "unreachable": unreachable, "bad": bad}
