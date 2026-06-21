"""Coverage ledger (#1) — the read→discover→re-query backbone of real deep research.

After each round ATHENA already fetches the top sources (``graph._read_top``). The ledger turns that
into a decision: it scores how well each sub-question and each named entity is actually covered by the
validated, on-topic evidence gathered so far, then the loop DRILLS the weakest cell next round instead
of refining blindly. The ledger is also streamed to the UI so a user/judge can watch coverage fill in.
"""

REL_FLOOR = 0.5      # a hit "covers" a cell only if it's at least this relevant
COVERED_AT = 0.5     # a cell counts as covered once its score reaches this


def _subq(entry: dict) -> str:
    return (entry.get("subq") or "").strip()


def _blob(entry: dict) -> str:
    hit = entry.get("hit")
    title = getattr(hit, "title", "") if hit else ""
    body = entry.get("content") or (getattr(hit, "snippet", "") if hit else "") or ""
    return f"{title} {body}".lower()


def compute_coverage(all_hits: dict, questions: list[str], entities: list[str] | None = None) -> dict:
    """Score coverage per sub-question (validated + relevant evidence attributed to it) and per named
    entity (does any gathered source actually mention it). Returns cells/entities/overall."""
    questions = [q for q in (questions or []) if q and q.strip()]
    entities = [e for e in (entities or []) if e and e.strip()]
    entries = list(all_hits.values())

    cells = []
    for q in questions:
        relevant = validated = 0
        best = 0.0
        for e in entries:
            if _subq(e) != q:
                continue
            r = float(e.get("relevance", 0.0) or 0.0)
            best = max(best, r)
            if r >= REL_FLOOR:
                relevant += 1
            if e.get("validated"):
                validated += 1
        # a facet is covered by EITHER authority (validated sources) OR breadth (several relevant
        # sources): a niche facet with lots of on-topic evidence but no Tier-A domain is still covered,
        # so the loop doesn't keep drilling a facet that simply has no authoritative source.
        score = min(validated / 2.0, 1.0) * 0.5 + min(relevant / 4.0, 1.0) * 0.5
        cells.append({"question": q, "validated": validated, "relevant": relevant,
                      "best_relevance": round(best, 3), "score": round(score, 3)})

    ent_cov = []
    if entities:
        blobs = [_blob(e) for e in entries]
        for ent in entities:
            el = ent.lower()
            n = sum(1 for b in blobs if el in b)
            ent_cov.append({"entity": ent, "hits": n, "covered": n > 0})

    covered = sum(1 for c in cells if c["score"] >= COVERED_AT)
    overall = round(covered / len(cells), 3) if cells else 0.0
    return {"cells": cells, "entities": ent_cov, "overall": overall}


def weakest_questions(coverage: dict, n: int = 2) -> list[str]:
    """The under-covered sub-questions to drill next, weakest first (only those below COVERED_AT)."""
    cells = sorted(coverage.get("cells", []), key=lambda c: c["score"])
    return [c["question"] for c in cells[:n] if c["score"] < COVERED_AT]


def is_complete(coverage: dict) -> bool:
    """Whether coverage is good enough to stop: every sub-question cell clears COVERED_AT (no weak
    cells left to drill). Empty ledger -> not complete (nothing has been measured yet)."""
    cells = coverage.get("cells", [])
    if not cells:
        return False
    return not weakest_questions(coverage, n=len(cells))


def uncovered_entities(coverage: dict) -> list[str]:
    """Named entities not mentioned by any gathered source — candidates for a targeted query."""
    return [e["entity"] for e in coverage.get("entities", []) if not e["covered"]]


def coverage_note(coverage: dict) -> str:
    """One-line summary of the weakest cells, appended to the controller's findings so reflection
    can see WHAT is thin, not just the titles."""
    weak = weakest_questions(coverage, n=3)
    unc = uncovered_entities(coverage)
    parts = []
    if weak:
        parts.append("Under-covered sub-questions: " + "; ".join(weak))
    if unc:
        parts.append("Entities with no evidence yet: " + ", ".join(unc))
    return (" | ".join(parts)) if parts else ""
