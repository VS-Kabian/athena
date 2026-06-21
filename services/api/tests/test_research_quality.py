"""Regression tests for the research-quality improvements (#1 validation, #2 evidence budget, #3 coverage)."""
import pytest
from unittest.mock import patch

from athena.agents.quality import quality_score, VALIDATION_TARGET
from athena.agents.validator import is_validated
from athena.agents import synthesizer


# ── #1: validation credits ABSOLUTE authoritative count, not the validated/discovered ratio ──
def test_validation_rewards_absolute_count_not_ratio():
    full = quality_score(discovered=52, validated=VALIDATION_TARGET, hallucination_risk=0.1, rounds=5)
    assert full["breakdown"]["validation"] == 22                  # target met -> full credit
    # discovering MORE blogs must not lower validation for the same validated count (the old ratio bug)
    more = quality_score(discovered=300, validated=VALIDATION_TARGET, hallucination_risk=0.1, rounds=5)
    assert more["breakdown"]["validation"] == 22
    # a single primary source is honestly low, but no longer ~0 (old run scored 1/22)
    one = quality_score(discovered=52, validated=1, hallucination_risk=0.1, rounds=5)
    assert one["breakdown"]["validation"] >= 3


# ── #1: more authoritative dev/vendor/press domains now count as validated ──
def test_more_authoritative_domains_validate():
    for url in ("https://aws.amazon.com/blogs/x", "https://venturebeat.com/ai/x",
                "https://docs.github.com/en/x", "https://blog.langchain.dev/x",
                "https://cloud.google.com/vertex-ai/docs"):
        assert is_validated(url), url
    assert not is_validated("https://some-random-seo-blog.io/top-10-frameworks-2026")


# ── #2: the writer now sees up to 2 chunks per source (was 1) ──
@pytest.mark.asyncio
async def test_synthesize_feeds_multiple_chunks_per_source():
    captured = {}

    async def fake_complete(provider, model, messages, api_key, **kw):
        captured["user"] = messages[-1]["content"]
        return "# Report\n\nBody [1]."

    ev = [{"url": "https://a.com", "text": "FIRST chunk of the page.", "score": 1.0},
          {"url": "https://a.com", "text": "SECOND chunk of the page.", "score": 0.9}]
    with patch.object(synthesizer, "complete", side_effect=fake_complete):
        await synthesizer.synthesize("topic", ev, {"provider": "g", "model": "m", "api_key": "k"})
    assert "FIRST chunk" in captured["user"] and "SECOND chunk" in captured["user"]


# ── #3: per-entity coverage directive lists every named subject in the prompt ──
@pytest.mark.asyncio
async def test_synthesize_includes_per_entity_directive():
    captured = {}

    async def fake_complete(provider, model, messages, api_key, **kw):
        captured["user"] = messages[-1]["content"]
        return "# Report\n\nLangGraph [1]."

    ev = [{"url": "https://a.com", "text": "evidence about frameworks", "score": 1.0}]
    with patch.object(synthesizer, "complete", side_effect=fake_complete):
        await synthesizer.synthesize("compare frameworks", ev,
                                     {"provider": "g", "model": "m", "api_key": "k"},
                                     entities=["LangGraph", "CrewAI", "Google ADK"])
    u = captured["user"]
    assert "REQUIRED COVERAGE" in u
    assert "LangGraph" in u and "CrewAI" in u and "Google ADK" in u
