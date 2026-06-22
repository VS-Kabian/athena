import re
from datetime import datetime, timezone

_YEAR_OLD = re.compile(r"\b20(1[0-9]|2[0-3])\b")  # 2010-2023

# topics that ask for the CURRENT/LATEST state, pricing, releases, or a recent year are time-sensitive:
# retrieval should bias toward fresh sources for them (P1-6).
_TIME_SENSITIVE = re.compile(
    r"\b(latest|newest|current|currently|recent|recently|today|this year|right now|nowadays|"
    r"20(2[4-9]|3[0-9])|pric(e|es|ing)|cost|release[ds]?|launch(ed|es)?|state of the art|sota|"
    r"trend|trends|upcoming|as of)\b", re.I)


def recency_query(question: str) -> str | None:
    """A recency-biased query variant for a time-sensitive question (latest/current state, pricing,
    releases, a recent year, ...), else None — so retrieval surfaces fresh sources instead of stale
    top-ranked pages. Year is taken from the clock so it never goes stale."""
    if not question or not _TIME_SENSITIVE.search(question):
        return None
    return f"{question} latest {datetime.now(timezone.utc).year}"


def _freshness(title: str, url: str) -> float:
    blob = f"{title or ''} {url or ''}"
    # 2024 is recent (current year 2026) — boost it too, closing the dead band where 2024 sources
    # were treated like undated ones (neither boosted nor penalized).
    if "2026" in blob or "2025" in blob or "2024" in blob:
        return 0.12
    if _YEAR_OLD.search(blob):
        return -0.10
    return 0.0


def select_sources(all_hits: dict, n: int = 20, entities: list[str] | None = None) -> list[dict]:
    entries = list(all_hits.values())
    for e in entries:
        # weight trust slightly above relevance so authoritative sources win ties (raises citation authority)
        e["select_score"] = (0.55 * float(e.get("trust", 0.0)) + 0.45 * float(e.get("relevance", 0.0))
                             + (0.15 if e.get("validated") else 0.0)
                             + _freshness(e["hit"].title, e["hit"].url))
    by_type: dict[str, list] = {}
    for e in entries:
        by_type.setdefault(e.get("source_type", "web"), []).append(e)
    selected, seen = [], set()

    def _add(e):
        selected.append(e); seen.add(e["hit"].url)

    # Reserve passes (a) and (b) both respect `n` so mandatory sources can't be pushed past the cap
    # and dropped by the final [:n]. Per-entity coverage runs first because the advertised invariant
    # is ">=1 source per named entity"; type diversity then fills any remaining reserved slots.

    # (b) per-entity coverage: guarantee >=1 good source mentioning each named entity
    def _mentions(e, el):
        return (el in (e["hit"].title or "").lower()
                or el in (e["hit"].snippet or "").lower()
                or el in (e.get("content") or "").lower())

    for ent in (entities or []):
        if len(selected) >= n:
            break
        el = ent.lower()
        if any(_mentions(e, el) for e in selected):
            continue
        cands = [e for e in entries if e["hit"].url not in seen and _mentions(e, el)]
        if cands:
            _add(max(cands, key=lambda e: e["select_score"]))

    # (a) authoritative type diversity
    for t in ("paper", "github", "docs"):
        if len(selected) >= n:
            break
        group = by_type.get(t)
        if group:
            best = max(group, key=lambda e: e["select_score"])
            if best["hit"].url not in seen:
                _add(best)

    # (c) fill the rest by score
    for e in sorted(entries, key=lambda e: e["select_score"], reverse=True):
        if e["hit"].url in seen:
            continue
        _add(e)
        if len(selected) >= n:
            break
    return selected[:n]


def assemble_content(selected: list[dict], docs: dict, *, with_provenance: bool = False):
    """Per-source content for synthesis: specialist/extracted content > fetched page > snippet fallback.

    Tolerant of redirect-canonicalized fetch keys — ``fetch_many`` follows redirects, so a page can come
    back under a normalized URL; we fall back to a normalized lookup so a selected source whose full page
    WAS fetched is never silently assembled from its one-line snippet (which would weaken grounding).

    With ``with_provenance=True`` also returns a parallel ``{url: 'full'|'fetched'|'snippet'}`` map so
    callers can down-weight snippet-only sources, which shouldn't carry full citation authority."""
    norm = {u.rstrip("/").lower(): t for u, t in docs.items()}
    content: dict = {}
    provenance: dict = {}
    for e in selected:
        url = e["hit"].url
        fetched = docs.get(url) or norm.get(url.rstrip("/").lower())
        if e.get("content"):
            content[url] = e["content"]; provenance[url] = "full"
        elif fetched:
            content[url] = fetched; provenance[url] = "fetched"
        elif e["hit"].snippet:
            content[url] = e["hit"].snippet; provenance[url] = "snippet"
    return (content, provenance) if with_provenance else content


def _title_sig(title: str) -> set:
    t = re.sub(r"20\d\d", " ", (title or "").lower())
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return {w for w in t.split() if len(w) > 2}


def dedup_near(all_hits: dict, threshold: float = 0.8) -> dict:
    """Drop near-duplicate titles (e.g. many 'LangGraph vs CrewAI vs AutoGen' posts),
    keeping the highest trust+relevance one. Returns a new {url_key: entry} dict."""
    entries = sorted(all_hits.values(),
                     key=lambda e: float(e.get("trust", 0)) + float(e.get("relevance", 0)), reverse=True)
    kept_sigs, out = [], {}
    for e in entries:
        url = e["hit"].url.rstrip("/").lower()
        sig = _title_sig(e["hit"].title)
        if not sig:
            out[url] = e
            continue
        dup = False
        for ks in kept_sigs:
            inter = len(sig & ks)
            union = len(sig | ks) or 1
            if inter / union >= threshold:
                dup = True
                break
        if not dup:
            kept_sigs.append(sig)
            out[url] = e
    return out
