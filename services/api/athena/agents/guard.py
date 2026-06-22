import re
from ..embed import embed_query, embed_passages, cosine
from .entail import _CITED, _META, _ABOUT_SOURCES, _clean_claim   # shared claim definition (kept consistent)

# Default cosine support bar. STRICT_THRESHOLD is used by the orchestrator when cosine is the SOLE
# grounding signal (entailment unavailable): cosine is symmetric and can't see contradiction, so a higher
# bar is required before loose topical overlap is allowed to pass as "supported".
DEFAULT_THRESHOLD = 0.55
STRICT_THRESHOLD = 0.62


def _sentences(markdown: str) -> list[str]:
    body = re.split(r"##\s*Sources", markdown)[0]
    body = re.sub(r"[#*`>_]", " ", body)
    parts = re.split(r"(?<=[.!?])\s+|\n+", body)
    return [s.strip() for s in parts if len(s.strip()) > 25]


def _domain(url: str) -> str:
    """Normalized registered-ish host for independence clustering: drop scheme + www./m. so mirrors and
    syndicated copies on the same site collapse to one domain (P2-8)."""
    from urllib.parse import urlparse
    h = (urlparse(url or "").hostname or "").lower()
    for pre in ("www.", "m."):
        if h.startswith(pre):
            h = h[len(pre):]
    return h


def factcheck(markdown: str, source_texts_in_order: list[str], threshold: float = 0.55,
              evidence_chunks: list[list[str]] | None = None, source_urls: list[str] | None = None) -> dict:
    """Verify each cited sentence against its cited source (embedding cosine) AND check
    cross-source corroboration — how many *independent* sources support the claim. Claims backed
    by only one source are listed in ``single_source`` (weak consensus); ``consensus`` is the
    fraction of claims supported by >=2 sources. risk = unsupported / total.

    ``evidence_chunks`` (P1-2): the EXACT chunks shown to the synthesizer, aligned to
    ``source_texts_in_order`` (``evidence_chunks[idx]`` = the chunks for source idx). When supplied for a
    source, the check embeds those instead of re-chunking the first 6000 chars of the raw page — so a claim
    supported by a passage deep in a long source isn't falsely flagged. Falls back to re-chunking when a
    source has no supplied chunks (back-compatible)."""
    sents = _sentences(markdown)
    cited = [s for s in sents if re.search(r"\[\d+\]", s)]
    target = cited if cited else sents
    nsrc = len(source_texts_in_order)
    cache: dict[int, list] = {}

    def _emb(idx: int) -> list:
        if idx not in cache:
            shown = evidence_chunks[idx] if evidence_chunks and idx < len(evidence_chunks) else None
            if shown:
                chunks = list(shown)
            else:
                txt = source_texts_in_order[idx]
                chunks = [txt[i:i + 600] for i in range(0, min(len(txt), 6000), 600)] or ([txt] if txt else [])
            cache[idx] = embed_passages(chunks) if chunks else []
        return cache[idx]

    total = unsupported = corroborated = 0
    flagged: list[str] = []
    single_source: list[str] = []
    for s in target:
        total += 1
        is_insufficient = "insufficient evidence" in s.lower()
        nums = [int(n) for n in re.findall(r"\[(\d+)\]", s)]
        cited_idxs = [n - 1 for n in nums if 0 <= n - 1 < nsrc]
        if not cited_idxs:
            # uncited claim or out-of-range [n]: unsupported by default (never match against "any" source).
            if not is_insufficient:
                unsupported += 1
                flagged.append(s)
            continue
        cvec = embed_query(s)

        def _supports(idx: int) -> bool:
            return any(cosine(cvec, v) >= threshold for v in _emb(idx))

        if not any(_supports(i) for i in cited_idxs):
            if not is_insufficient:
                unsupported += 1
                flagged.append(s)
            continue
        # cross-source corroboration: is the claim ALSO supported by an INDEPENDENT source? When source
        # URLs are supplied, count DISTINCT domains (excluding the cited source's own domain) so mirrors /
        # syndicated copies on the same host can't fake cross-source agreement (P2-8). Falls back to raw
        # source indices (every source independent) when URLs are absent — preserves prior behavior.
        cited_doms = {_domain(source_urls[i]) for i in cited_idxs} if source_urls else set()
        other_doms = set()
        for j in range(nsrc):
            if j in cited_idxs or not _supports(j):
                continue
            d = _domain(source_urls[j]) if source_urls else str(j)
            if d and d not in cited_doms:
                other_doms.add(d)
        if other_doms:
            corroborated += 1
        elif not is_insufficient:
            single_source.append(s)
    risk = round(unsupported / total, 3) if total else 0.0
    consensus = round(corroborated / total, 3) if total else 0.0
    return {"risk": risk, "total": total, "unsupported": unsupported, "flagged": flagged,
            "single_source": single_source, "consensus": consensus}


def enforce_grounding(markdown: str, n_sources: int) -> tuple[str, dict]:
    """Write-time claim-grounding gate (P0-2A). Detect factual sentences in the report BODY that carry no
    VALID in-range ``[n]`` citation — they are unsupported by construction (the single biggest
    reduce-at-source lever). Returns ``(markdown, report)`` where ``report = {"uncited": int,
    "claims": [str, ...]}``; the count feeds the honest risk aggregate and the claims surface as flags.

    Non-destructive: the markdown is returned unchanged — this layer only DETECTS and counts. (Rewriting
    an uncited sentence to either attach a real citation or hedge it is the LLM ``cite-or-cut`` pass, a
    later step.) Detection is conservative on purpose — only real prose assertions (sentences ending in
    ``.``/``!``/``?``) are judged, and the same framing / about-the-sources / 'insufficient evidence'
    filters used by the entailment judge exclude headings, scaffolding and self-referential prose — so the
    metric is never inflated by flagging structure as a claim.
    """
    body = re.split(r"##\s*Sources", markdown)[0]
    uncited: list[str] = []
    for raw in re.split(r"(?<=[.!?])\s+|\n+", body):
        raw = raw.strip()
        if not raw or raw.startswith("#"):          # blank line or heading -> not a claim
            continue
        if raw[-1] not in ".!?":                    # not a finished prose sentence (table row / label) -> skip
            continue
        s = _clean_claim(raw)
        if len(s) < 25:                             # too short after cleaning to be a real claim
            continue
        if _META.search(s) or _ABOUT_SOURCES.search(s) or "insufficient evidence" in s.lower():
            continue                                # framing / about-the-sources / placeholder -> not a claim
        nums = [int(n) for n in _CITED.findall(raw)]
        if any(1 <= n <= n_sources for n in nums):  # at least one valid in-range citation -> grounded
            continue
        uncited.append(s)                           # no citation, or only out-of-range [n] -> unsupported
    return markdown, {"uncited": len(uncited), "claims": uncited}
