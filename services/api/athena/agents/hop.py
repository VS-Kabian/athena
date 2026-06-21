"""Multi-hop citation chasing (Upgrade 1) — the depth mechanism.

A flat `search -> read -> write` loop cites whatever search returned, which skews to blog round-ups.
Real deep-research reaches PRIMARY sources by following a page's own references: read a page, harvest
its outbound links, rank them by domain authority + topic relevance, and fetch a BOUNDED second hop
(one hop only). The fetched primaries join the pool (with their parent's facet) so they count toward
coverage, selection, evidence, and the trust ledger — just like any other source.

Best-effort and bounded: a chase failure never sinks a run, fetches are SSRF-guarded, and there is no
third hop.
"""
import asyncio
import re
from urllib.parse import urljoin, urlparse

from .. import cache
from ..api.events import bus
from ..fetch import fetch_html, fetch_many
from ..log import get_logger
from ..search.base import SearchHit
from ..search.relevance import filter_by_relevance
from .validator import is_validated, score_source

log = get_logger(__name__)

_HREF = re.compile(r'href=["\']([^"\']+)["\']', re.I)
_SKIP_SCHEME = ("javascript:", "mailto:", "tel:", "data:")
_ASSET = (".css", ".js", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".woff", ".woff2", ".mp4", ".zip")
MAX_LINKS_PER_PAGE = 40
MAX_HOPS_PER_ROUND = 5    # bounded 2nd-hop fetches per chase
PARENT_N = 6              # harvest links from the strongest N already-read sources
REL_FLOOR = 0.45         # drop off-topic chased pages (mirrors specialist seeding)


def _classify(url: str) -> str:
    u = url.lower()
    if "github.com" in u: return "github"
    if "arxiv.org" in u or "doi.org" in u or "semanticscholar" in u: return "paper"
    if "docs." in u or "/docs" in u: return "docs"
    if "medium.com" in u or "substack" in u or "blog" in u: return "blog"
    if "news" in u: return "news"
    return "web"


def extract_links(html: str, base_url: str) -> list[str]:
    """Absolute http(s) outbound links from a page, relative URLs resolved against base_url, deduped,
    with non-navigational schemes and static assets dropped."""
    if not html:
        return []
    out, seen = [], set()
    for m in _HREF.finditer(html):
        href = m.group(1).strip()
        if not href or href.lower().startswith(_SKIP_SCHEME):
            continue
        url = urljoin(base_url, href.split("#")[0])   # resolve relative, drop fragment
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname:
            continue
        low = url.lower()
        if any(low.endswith(ext) for ext in _ASSET):
            continue
        key = low.rstrip("/")
        if key in seen:
            continue
        seen.add(key)
        out.append(url)
        if len(out) >= MAX_LINKS_PER_PAGE:
            break
    return out


def rank_links(topic: str, links: list[str], seen_keys: set, k: int) -> list[str]:
    """Keep unseen links and rank by domain authority (validator) + light topic-term overlap in the URL.
    SSRF is NOT checked here (it would do DNS per link) — the actual fetch re-validates every URL."""
    terms = {w for w in re.findall(r"[a-z0-9]{4,}", topic.lower())}
    scored = []
    for url in links:
        key = url.rstrip("/").lower()
        if key in seen_keys:
            continue
        authority = score_source(url)                                   # 0..1, no DNS
        overlap = sum(1 for t in terms if t in url.lower()) * 0.05
        scored.append((authority + overlap, url))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [u for _, u in scored[:k]]


async def _harvest(url: str) -> list[str]:
    """Outbound links of a page, cached for a day so re-runs don't re-download."""
    ck = cache.skey("links", url)
    cached = await cache.get_json(ck)
    if cached is not None:
        return cached
    html = await fetch_html(url)
    links = extract_links(html or "", url)
    await cache.set_json(ck, links, ttl=86400)
    return links


def _title_from(text: str, url: str) -> str:
    first = (text or "").strip().split("\n", 1)[0].strip()
    return first if 10 < len(first) <= 120 else url


async def chase(run_id: str, topic: str, all_hits: dict, rnd: int,
                k: int = MAX_HOPS_PER_ROUND, parent_n: int = PARENT_N) -> int:
    """One bounded second hop. From the strongest already-READ sources, harvest outbound links, rank by
    authority/relevance, fetch the top-k new ones (SSRF-guarded), rerank for honest on-topic relevance,
    and add the survivors to ``all_hits`` (attributed to their parent's facet). Returns #added."""
    read = sorted((e for e in all_hits.values() if e.get("content")),
                  key=lambda e: e.get("relevance", 0.0), reverse=True)[:parent_n]
    if not read:
        return 0
    seen = set(all_hits.keys())
    harvested = await asyncio.gather(*[_harvest(e["hit"].url) for e in read], return_exceptions=True)
    subq_by_key: dict[str, str] = {}
    cand: list[str] = []
    for e, links in zip(read, harvested):
        if isinstance(links, Exception) or not links:
            continue
        for u in links:
            key = u.rstrip("/").lower()
            if key in seen or key in subq_by_key:
                continue
            subq_by_key[key] = e.get("subq", "")
            cand.append(u)
    if not cand:
        return 0
    ranked = rank_links(topic, cand, seen, k)
    if not ranked:
        return 0
    docs = await fetch_many(ranked, limit=k)
    if not docs:
        return 0

    hits = [(SearchHit(url=u, title=_title_from(t, u), snippet=t[:300], rank=0, provider="hop"), t)
            for u, t in docs.items()]
    kept = await asyncio.to_thread(filter_by_relevance, topic, [h for h, _ in hits])   # sets .relevance
    keep_rel = {h.url: getattr(h, "relevance", 0.0) for h in kept}
    added = 0
    for h, text in hits:
        rel = keep_rel.get(h.url)
        if rel is None or rel < REL_FLOOR:
            continue
        key = h.url.rstrip("/").lower()
        if key in all_hits:
            continue
        h.relevance = rel
        stype = _classify(h.url)
        trust = score_source(h.url, h.title)
        valid = is_validated(h.url, h.title) and rel >= 0.4
        sq = subq_by_key.get(key, "")
        all_hits[key] = {"hit": h, "round": rnd, "source_type": stype, "trust": trust,
                         "validated": valid, "relevance": rel, "subq": sq, "content": text, "hop": 2}
        await bus.publish(run_id, {"type": "source", "data": {
            "url": h.url, "title": h.title, "provider": "hop", "source_type": stype, "round": rnd,
            "trust": trust, "validated": valid, "relevance": rel, "providers": ["hop"], "subquestion": sq}})
        added += 1
    if added:
        await bus.publish(run_id, {"type": "hop", "data": {"round": rnd, "added": added}})
    return added
