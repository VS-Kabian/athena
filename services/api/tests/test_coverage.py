"""Coverage ledger (#1): per sub-question / entity coverage scoring + weakest-cell selection."""
from athena.search.base import SearchHit
from athena.agents.coverage import (compute_coverage, weakest_questions,
                                     uncovered_entities, coverage_note)


def _entry(subq, relevance, validated, title="t", snippet="s", content=""):
    return {"hit": SearchHit(url="https://x.com", title=title, snippet=snippet, rank=0, provider="p"),
            "subq": subq, "relevance": relevance, "validated": validated, "content": content}


def test_well_covered_question_scores_high_thin_one_scores_low():
    qs = ["strong q", "thin q"]
    all_hits = {
        "a": _entry("strong q", 0.8, True),
        "b": _entry("strong q", 0.7, True),
        "c": _entry("strong q", 0.6, False),
        # thin q: a single weakly-relevant, unvalidated hit
        "d": _entry("thin q", 0.3, False),
    }
    cov = compute_coverage(all_hits, qs)
    cells = {c["question"]: c for c in cov["cells"]}
    assert cells["strong q"]["score"] >= 0.5
    assert cells["thin q"]["score"] < 0.5
    assert weakest_questions(cov) == ["thin q"]


def test_entity_coverage_detects_missing_subject():
    qs = ["q"]
    all_hits = {
        "a": _entry("q", 0.9, True, title="Comparing LangGraph internals", content="LangGraph is a framework"),
    }
    cov = compute_coverage(all_hits, qs, entities=["LangGraph", "CrewAI"])
    ent = {e["entity"]: e for e in cov["entities"]}
    assert ent["LangGraph"]["covered"] is True
    assert ent["CrewAI"]["covered"] is False
    assert "CrewAI" in uncovered_entities(cov)
    assert "CrewAI" in coverage_note(cov)


def test_facet_covered_by_relevant_breadth_without_validation():
    # a facet with lots of on-topic sources but no Tier-A validated domain is still "covered"
    qs = ["q"]
    all_hits = {f"u{i}": _entry("q", 0.7, False) for i in range(4)}   # 4 relevant, 0 validated
    cov = compute_coverage(all_hits, qs)
    assert cov["cells"][0]["score"] >= 0.5
    assert weakest_questions(cov) == []                              # not flagged for drilling


def test_empty_inputs_are_safe():
    cov = compute_coverage({}, [])
    assert cov["cells"] == [] and cov["overall"] == 0.0
    assert weakest_questions(cov) == [] and uncovered_entities(cov) == []
    assert coverage_note(cov) == ""
