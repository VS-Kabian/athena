import asyncio
import dataclasses
from dataclasses import asdict

from .base import SearchHit
from .merge import rrf_merge
from .. import cache
from ..log import get_logger

log = get_logger(__name__)


def _seed_providers(hits: list[SearchHit]) -> None:
    """single/priority hits bypass rrf_merge, so `providers` stays []. Seed it with the hit's own
    provider so the UI provider chips / persisted metadata aren't empty downstream. Copy-on-write
    (replace in place) to avoid mutating hits shared with the provider cache."""
    for i, h in enumerate(hits or []):
        if not h.providers:
            hits[i] = dataclasses.replace(h, providers=[h.provider])


def _retry_after_seconds(e) -> float | None:
    """Classify a provider HTTP error for retry (P1-8). For a 429/5xx, return a BOUNDED backoff that
    honors a `Retry-After` header (so a rate-limited but recoverable provider isn't silently dropped).
    For a hard 4xx (404/403/401), return -1.0 (do NOT retry — it won't recover). Otherwise None
    (unknown error → use the default short backoff)."""
    resp = getattr(e, "response", None)
    code = getattr(resp, "status_code", None)
    if code is None:
        return None
    if code == 429 or code >= 500:
        try:
            ra = float((getattr(resp, "headers", None) or {}).get("Retry-After", ""))
        except (TypeError, ValueError):
            ra = 0.0
        return min(ra if ra > 0 else 0.8, 5.0)   # bounded so a hostile Retry-After can't stall the run
    if 400 <= code < 500:
        return -1.0                              # hard client error -> not retryable
    return None


async def _safe(provider, query, k):
    # one quick retry on a transient error (a timeout already waited 8s, so don't retry that). A 429/5xx
    # backs off honoring Retry-After; a hard 4xx is not retried.
    for attempt in range(2):
        try:
            return await asyncio.wait_for(provider.search(query, k), timeout=8)
        except asyncio.TimeoutError:
            log.warning("search provider %s timed out", getattr(provider, "name", "?"))
            return []
        except Exception as e:
            backoff = _retry_after_seconds(e)
            if attempt == 1 or backoff == -1.0:
                log.warning("search provider %s failed: %s", getattr(provider, "name", "?"), e)
                return []
            await asyncio.sleep(backoff if backoff is not None else 0.4)


async def multi_search(query: str, providers: list, mode: str = "broadcast", k: int = 10) -> list[SearchHit]:
    if not providers:
        return []
    names = ",".join(getattr(p, "name", "?") for p in providers)
    ck = cache.skey("search", query, mode, names, k)
    cached = await cache.get_json(ck)
    if cached is not None:
        return [SearchHit(**d) for d in cached]

    if mode == "single":
        result = await _safe(providers[0], query, k)
        _seed_providers(result)
    elif mode == "priority":
        result = []
        for p in providers:
            hits = await _safe(p, query, k)
            if hits:
                result = hits
                break
        _seed_providers(result)
    else:  # broadcast
        lists = await asyncio.gather(*[_safe(p, query, k) for p in providers])
        result = rrf_merge([l for l in lists if l], k=60)

    # cache real results for a few hours (research moves fast; 24h was too stale and made re-runs of a
    # topic replay old rounds instantly), but an empty result only briefly so a transient provider
    # outage doesn't negative-cache "no results" for this query.
    await cache.set_json(ck, [asdict(h) for h in result], ttl=21600 if result else 600)
    return result
