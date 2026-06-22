"""Reference-free re-verification (P1-4) — a Chain-of-Verification / Corrective-RAG style pass.

The entailment judge only compares a claim to its CITED source. If that source is itself wrong, or the
claim subtly misreads a correct source, entailment can still mark it "supported" — the classic
"cited-but-wrong" failure. This module re-checks the highest-risk claims against a FRESH, independent web
search (not the cited source) and flags any that a fresh source refutes.

It is best-effort and dependency-injected: ``search`` and ``fetch`` (and ``entail``) are passed in so the
orchestrator can bind real providers while tests inject deterministic mocks. Any failure on a single claim
is swallowed so a re-check problem never breaks a run. Gated behind deep mode by the caller.
"""
import re

from .entail import entail_report

_CITED = re.compile(r"\s*\[\d+\]")


def _neutral_query(claim: str) -> str:
    """A neutral search query for a claim: drop citation markers, keep the assertion text, bound length."""
    return _CITED.sub("", claim or "").strip()[:200]


def _hit_url(h):
    return getattr(h, "url", None) or (h.get("url") if isinstance(h, dict) else None)


async def recheck_claims(verdicts: list[dict], topic: str, llm: dict | None, *,
                         search, fetch, entail=entail_report, k: int = 2,
                         per_claim_sources: int = 3) -> list[dict]:
    """Re-verify the top-``k`` highest-risk claims (refuted worst, then NEI; supported claims are skipped)
    against fresh, independent sources. ``search(query) -> hits`` and ``fetch(urls) -> {url: text}`` are
    injected. Returns a list of ``{claim, refuted_by_fresh, engine}`` for each claim actually re-checked."""
    if not verdicts or not llm:
        return []
    risky = [v for v in verdicts if str(v.get("verdict")) in ("refuted", "nei")]
    risky.sort(key=lambda v: 0 if v.get("verdict") == "refuted" else 1)   # refuted first
    out: list[dict] = []
    for v in risky[:k]:
        claim = (v.get("claim") or "").strip()
        q = _neutral_query(claim)
        if not q:
            continue
        try:
            hits = await search(q) or []
            urls = [u for u in (_hit_url(h) for h in hits) if u][:per_claim_sources]
            docs = await fetch(urls) if urls else {}
            fresh = [docs[u] for u in urls if docs.get(u)]
            if not fresh:
                continue   # nothing fresh to check against -> can't refute; leave the entailment verdict as-is
            # entail the claim against ONLY the fresh sources (cite them [1..n]); a refutation here means
            # an independent source contradicts what the cited source seemed to support.
            markers = " ".join(f"[{i + 1}]" for i in range(len(fresh)))
            srcs = "\n".join(f"{i + 1}. fresh-source-{i + 1}" for i in range(len(fresh)))
            md = f"## Recheck\n{claim} {markers}\n\n## Sources\n{srcs}"
            rep = await entail(md, fresh, llm)
            out.append({"claim": claim,
                        "refuted_by_fresh": bool((rep.get("refuted", 0) or 0) > 0),
                        "engine": rep.get("engine")})
        except Exception:
            continue   # best-effort: a single claim's re-check failing never sinks the rest
    return out
