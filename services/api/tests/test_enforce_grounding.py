"""Write-time claim-grounding gate (P0-2A): factual body sentences with no valid in-range [n] are
unsupported by construction and must be counted (they feed the honest risk aggregate). Detection is
conservative — headings, framing, 'insufficient evidence' placeholders, and the Sources list are never
flagged, so the metric is never inflated by structure."""
from athena.agents.guard import enforce_grounding


def test_uncited_factual_sentence_is_flagged_and_counted():
    md = ("# Report\n\n## Findings\n"
          "LangGraph is a graph-based agent framework used widely in production systems.\n"   # uncited
          "CrewAI is a role-based multi-agent orchestration library [1].\n\n"                 # cited -> clean
          "## Sources\n1. https://a.com")
    out, report = enforce_grounding(md, n_sources=1)
    assert out == md                                          # non-destructive: body unchanged
    assert report["uncited"] == 1
    assert any("LangGraph is a graph-based" in c for c in report["claims"])
    assert not any("CrewAI" in c for c in report["claims"])   # the cited claim is not flagged


def test_fully_cited_report_has_zero_uncited():
    md = ("# Report\n\n"
          "LangGraph models agents as stateful directed graphs with conditional routing [1].\n"
          "CrewAI uses a role-based crew abstraction for multi-agent orchestration [2].\n\n"
          "## Sources\n1. a\n2. b")
    _, report = enforce_grounding(md, n_sources=2)
    assert report["uncited"] == 0


def test_headings_framing_and_placeholders_never_flagged():
    md = ("# Research Report: agent frameworks\n\n## Overview of the landscape\n"
          "This report examines the four leading agent frameworks in considerable depth.\n"   # framing
          "The following section compares their architectures and the relevant tradeoffs.\n"  # framing
          "_Insufficient evidence to complete this section._\n\n"                             # placeholder
          "## Sources\n1. a")
    _, report = enforce_grounding(md, n_sources=1)
    assert report["uncited"] == 0                             # nothing here is a real uncited claim


def test_out_of_range_citation_counts_as_uncited():
    md = ("# Report\n\n"
          "CrewAI reportedly reached nine hundred queries per second in published benchmarks [45].\n\n"
          "## Sources\n1. a\n2. b")
    _, report = enforce_grounding(md, n_sources=2)            # only [45], out of range
    assert report["uncited"] == 1
    assert any("nine hundred queries" in c for c in report["claims"])


def test_sources_section_is_not_scanned():
    md = ("# Report\n\nLangGraph is a graph-based framework for building agents [1].\n\n"
          "## Sources\n1. https://example.com/a-long-source-line-that-is-not-a-cited-claim")
    _, report = enforce_grounding(md, n_sources=1)
    assert report["uncited"] == 0


def test_table_rows_and_labels_are_not_flagged():
    # a table header row / a bare label has no terminal sentence punctuation -> conservatively skipped
    md = ("# Report\n\n| Framework | Architecture | Notes |\n"
          "Key tradeoffs to consider\n\n"
          "## Sources\n1. a")
    _, report = enforce_grounding(md, n_sources=1)
    assert report["uncited"] == 0
