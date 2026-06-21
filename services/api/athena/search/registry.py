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


async def _safe(provider, query, k):
    # one quick retry on a transient error (a timeout already waited 8s, so don't retry that)
    for attempt in range(2):
        try:
            return await asyncio.wait_for(provider.search(query, k), timeout=8)
        except asyncio.TimeoutError:
            log.warning("search provider %s timed out", getattr(provider, "name", "?"))
            return []
        except Exception as e:
            if attempt == 1:
                log.warning("search provider %s failed: %s", getattr(provider, "name", "?"), e)
                return []
            await asyncio.sleep(0.4)


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
