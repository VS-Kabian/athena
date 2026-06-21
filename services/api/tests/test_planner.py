import pytest
from unittest.mock import patch
from athena.agents.planner import decompose

@pytest.mark.asyncio
async def test_decompose_returns_subquestions():
    async def fake(*a, **k): return '["q1","q2","q3"]'
    with patch("athena.agents.planner.complete", side_effect=fake):
        qs = await decompose("topic", n=3, llm={"provider":"groq","model":"m","api_key":"k"})
        assert qs == ["q1","q2","q3"]

@pytest.mark.asyncio
async def test_decompose_falls_back_on_bad_json():
    async def fake(*a, **k): return "not json"
    with patch("athena.agents.planner.complete", side_effect=fake):
        qs = await decompose("quantum computing", n=2, llm={"provider":"groq","model":"m","api_key":"k"})
        assert len(qs) == 2 and all("quantum computing" in q for q in qs)

@pytest.mark.asyncio
async def test_decompose_falls_back_when_model_times_out():
    # a slow reasoning ("pro") model that times out must NOT propagate and kill the run
    async def boom(*a, **k): raise RuntimeError("litellm.Timeout: model timed out")
    with patch("athena.agents.planner.complete", side_effect=boom):
        qs = await decompose("quantum computing", n=3,
                             llm={"provider": "deepseek", "model": "deepseek-v4-pro", "api_key": "k"})
    assert len(qs) == 3 and all("quantum computing" in q for q in qs)


@pytest.mark.asyncio
async def test_planner_uses_extended_timeout_for_reasoning_models():
    seen = {}
    async def fake(*a, **k): seen["timeout"] = k.get("timeout"); return '["a","b","c"]'
    with patch("athena.agents.planner.complete", side_effect=fake):
        await decompose("t", n=3, llm={"provider": "deepseek", "model": "deepseek-v4-pro", "api_key": "k"})
    assert seen["timeout"] and seen["timeout"] >= 120  # generous for reasoning models


from athena.agents.planner import extract_entities

@pytest.mark.asyncio
async def test_extract_entities_parses_json():
    async def fake(*a, **k): return '["LangGraph", "CrewAI", "AutoGen"]'
    with patch("athena.agents.planner.complete", side_effect=fake):
        ents = await extract_entities("compare LangGraph CrewAI AutoGen", {"provider": "groq", "model": "m", "api_key": "k"})
        assert ents == ["LangGraph", "CrewAI", "AutoGen"]

@pytest.mark.asyncio
async def test_extract_entities_empty_on_bad_json():
    async def fake(*a, **k): return "no entities here"
    with patch("athena.agents.planner.complete", side_effect=fake):
        ents = await extract_entities("some topic", {"provider": "groq", "model": "m", "api_key": "k"})
        assert ents == []


from athena.agents.planner import expand_facets

LLM = {"provider": "groq", "model": "m", "api_key": "k"}


@pytest.mark.asyncio
async def test_expand_facets_returns_only_new_nonduplicate():
    # model proposes one duplicate of an existing facet + one genuinely new -> only the new survives
    async def fake(*a, **k): return '["Existing facet", "A brand new angle"]'
    with patch("athena.agents.planner.complete", side_effect=fake):
        out = await expand_facets("topic", ["Existing facet"], "findings", n=2, llm=LLM)
    assert out == ["A brand new angle"]


@pytest.mark.asyncio
async def test_expand_facets_caps_at_n():
    async def fake(*a, **k): return '["one", "two", "three"]'
    with patch("athena.agents.planner.complete", side_effect=fake):
        out = await expand_facets("topic", [], "findings", n=2, llm=LLM)
    assert out == ["one", "two"]


@pytest.mark.asyncio
async def test_expand_facets_empty_without_model_or_on_failure():
    assert await expand_facets("topic", ["a"], "f", llm=None) == []
    async def boom(*a, **k): raise RuntimeError("down")
    with patch("athena.agents.planner.complete", side_effect=boom):
        assert await expand_facets("topic", ["a"], "f", llm=LLM) == []
