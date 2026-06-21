"""Entailment verification (#2/#3): directional Supported/Refuted/NEI verdicts + conflict flags,
with a graceful fallback to the embedding (cosine) grounding signal."""
import json
import pytest
from unittest.mock import patch

from athena.agents import entail
from athena.agents.entail import entail_report, from_cosine, cited_sentences

MD = ("## Findings\nLangGraph is a graph-based agent framework [1].\n"
      "CrewAI reached exactly 900 QPS in published tests [2].\n\n## Sources\n1. a\n2. b")
SRC = ["LangGraph is a graph-based framework for building agents.",
       "CrewAI is a role-based multi-agent orchestration library."]
LLM = {"provider": "p", "model": "m", "api_key": "k"}


def _fake_returning(verdicts):
    async def fake(provider, model, messages, api_key, **kw):
        return json.dumps(verdicts)
    return fake


def test_cited_sentences_only_picks_cited():
    s = cited_sentences(MD)
    assert len(s) == 2 and all("[" in x for x in s)


@pytest.mark.asyncio
async def test_entailment_supported_and_refuted_counts():
    fake = _fake_returning([{"n": 1, "verdict": "supported", "confidence": 0.9, "conflict": False},
                            {"n": 2, "verdict": "refuted", "confidence": 0.8, "conflict": False}])
    with patch.object(entail, "complete", side_effect=fake):
        r = await entail_report(MD, SRC, LLM)
    assert r["engine"] == "entailment"
    assert r["supported"] == 1 and r["refuted"] == 1 and r["nei"] == 0
    assert r["risk"] == 0.5                                  # 1 of 2 not supported
    assert any("refuted" in f for f in r["flagged"])
    assert len(r["verdicts"]) == 2                           # per-claim audit trail


@pytest.mark.asyncio
async def test_cross_source_conflict_flagged():
    fake = _fake_returning([{"n": 1, "verdict": "supported", "confidence": 0.7, "conflict": True},
                            {"n": 2, "verdict": "supported", "confidence": 0.7, "conflict": False}])
    with patch.object(entail, "complete", side_effect=fake):
        r = await entail_report(MD, SRC, LLM)
    assert r["conflicts"] == 1
    assert r["conflict_items"] and any("conflict" in f.lower() for f in r["flagged"])


@pytest.mark.asyncio
async def test_falls_back_to_cosine_when_no_model():
    fc = {"total": 2, "unsupported": 1, "risk": 0.5, "flagged": [], "single_source": [], "consensus": 0.5}
    r = await entail_report(MD, SRC, None, factcheck=fc)
    assert r["engine"] == "embedding"
    assert r["supported"] == 1 and r["nei"] == 1 and r["risk"] == 0.5


@pytest.mark.asyncio
async def test_falls_back_when_model_covers_too_few_claims():
    # model produced no parseable verdicts at all -> below the _MIN_COVERAGE floor -> deterministic fallback
    async def fake(provider, model, messages, api_key, **kw):
        return "the model rambled and never produced JSON"
    fc = {"total": 2, "unsupported": 0, "risk": 0.0, "flagged": [], "single_source": [], "consensus": 1.0}
    with patch.object(entail, "complete", side_effect=fake):
        r = await entail_report(MD, SRC, LLM, factcheck=fc)
    assert r["engine"] == "embedding"


# ── Task 3: robustness on reasoning models ──
MD3 = ("## Findings\nLangGraph uses a graph-based runtime for agents [1].\n"
       "CrewAI is role-based and simple to start [2].\n"
       "AutoGen uses a conversational actor model [3].\n\n## Sources\n1. a\n2. b\n3. c")
SRC3 = ["LangGraph graph runtime", "CrewAI role based", "AutoGen actor model"]


@pytest.mark.asyncio
async def test_partial_coverage_above_floor_still_reports_entailment():
    # model judged 2 of 3 claims (0.67 >= 0.5 floor) -> still real entailment; the missing claim -> NEI
    fake = _fake_returning([{"n": 1, "verdict": "supported", "confidence": 0.9, "conflict": False},
                            {"n": 2, "verdict": "supported", "confidence": 0.8, "conflict": False}])
    with patch.object(entail, "complete", side_effect=fake):
        r = await entail_report(MD3, SRC3, LLM)
    assert r["engine"] == "entailment"          # no longer hides behind cosine on a partial pass
    assert r["total"] == 3 and r["supported"] == 2 and r["nei"] == 1


@pytest.mark.asyncio
async def test_entailment_parses_json_inside_markdown_fence():
    async def fake(provider, model, messages, api_key, **kw):
        return "```json\n[{\"n\": 1, \"verdict\": \"supported\", \"confidence\": 0.9, \"conflict\": false}," \
               "{\"n\": 2, \"verdict\": \"refuted\", \"confidence\": 0.8, \"conflict\": false}]\n```"
    with patch.object(entail, "complete", side_effect=fake):
        r = await entail_report(MD, SRC, LLM)
    assert r["engine"] == "entailment" and r["supported"] == 1 and r["refuted"] == 1


def test_extract_json_array_handles_fences_and_prose():
    from athena.agents.entail import _extract_json_array
    assert _extract_json_array('```json\n[{"n": 1}]\n```') == [{"n": 1}]
    assert _extract_json_array('Sure, here you go: [{"n": 1}] — done') == [{"n": 1}]
    assert _extract_json_array('[{"n": 1}]') == [{"n": 1}]
    assert _extract_json_array('no json here at all') is None
    assert _extract_json_array('') is None


def test_focus_includes_end_anchored_window_no_tail_gap():
    from athena.agents.entail import _focus
    # the only claim keyword lives past the last step-aligned window — the end anchor must still catch it
    text = ("x" * 1000) + " ZEBRAFACT here is the answer."
    win = _focus("what is ZEBRAFACT", text, 200)
    assert "ZEBRAFACT" in win


def test_focus_selects_the_claim_relevant_window():
    from athena.agents.entail import _focus
    # the supporting fact is buried far into a long page; _focus must surface that window, not the head
    text = ("filler intro paragraph. " * 60) + "LangGraph reached general availability version 1.0 in October 2025. " + ("trailing noise. " * 60)
    win = _focus("When did LangGraph reach general availability 1.0?", text, 200)
    assert "general availability version 1.0" in win
    assert len(win) <= 200


@pytest.mark.asyncio
async def test_nei_counts_less_than_refuted_toward_hallucination_risk():
    # two claims both marked NEI -> risk must be far below the 1.0 that two REFUTED claims would give
    nei = _fake_returning([{"n": 1, "verdict": "nei", "confidence": 0.5, "conflict": False},
                           {"n": 2, "verdict": "nei", "confidence": 0.5, "conflict": False}])
    with patch.object(entail, "complete", side_effect=nei):
        r = await entail_report(MD, SRC, LLM)
    assert r["nei"] == 2 and r["risk"] < 0.5          # NEI is softened, not treated as fabrication
    refuted = _fake_returning([{"n": 1, "verdict": "refuted", "confidence": 0.9, "conflict": False},
                               {"n": 2, "verdict": "refuted", "confidence": 0.9, "conflict": False}])
    with patch.object(entail, "complete", side_effect=refuted):
        r2 = await entail_report(MD, SRC, LLM)
    assert r2["risk"] == 1.0 and r2["risk"] > r["risk"]   # real contradictions still score full risk


def test_from_cosine_shape():
    r = from_cosine({"total": 5, "unsupported": 2, "risk": 0.4})
    assert r["engine"] == "embedding" and r["supported"] == 3 and r["nei"] == 2 and r["refuted"] == 0
