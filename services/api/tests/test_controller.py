import pytest
from unittest.mock import patch

from athena.agents.controller import reflect

LLM = {"provider": "groq", "model": "m", "api_key": "k"}


@pytest.mark.asyncio
async def test_reflect_stops_at_round_budget_without_calling_model():
    called = {"n": 0}

    async def fake(*a, **k):
        called["n"] += 1
        return "{}"

    with patch("athena.agents.controller.complete", side_effect=fake):
        out = await reflect("t", "f", ["q"], 3, 3, LLM)
    assert out["action"] == "stop" and called["n"] == 0


@pytest.mark.asyncio
async def test_reflect_parses_drill_with_questions():
    async def fake(*a, **k):
        return '{"action":"drill","questions":["q1","q2"],"reason":"gap in X"}'

    with patch("athena.agents.controller.complete", side_effect=fake):
        out = await reflect("t", "f", ["q"], 1, 3, LLM)
    assert out["action"] == "drill" and out["questions"] == ["q1", "q2"]


@pytest.mark.asyncio
async def test_reflect_parses_stop_embedded_in_prose():
    async def fake(*a, **k):
        return 'Sure thing: {"action":"stop","questions":[],"reason":"covered"} done'

    with patch("athena.agents.controller.complete", side_effect=fake):
        out = await reflect("t", "f", ["q"], 1, 3, LLM)
    assert out["action"] == "stop"


@pytest.mark.asyncio
async def test_reflect_falls_back_to_continue_on_bad_json():
    async def fake(*a, **k):
        return "not json at all"

    with patch("athena.agents.controller.complete", side_effect=fake):
        out = await reflect("t", "f", ["q"], 1, 3, LLM)
    assert out["action"] == "continue" and out["questions"] == []


@pytest.mark.asyncio
async def test_reflect_uses_generous_token_budget_for_reasoning_models():
    # reasoning ("pro") models spend tokens on internal reasoning before emitting JSON;
    # too small a budget returns empty -> "reflection unavailable". Keep it generous.
    seen = {}
    async def fake(*a, **k):
        seen["max_tokens"] = k.get("max_tokens")
        return '{"action":"continue","questions":[],"reason":"ok"}'
    with patch("athena.agents.controller.complete", side_effect=fake):
        await reflect("t", "f", ["q"], 1, 5, LLM)
    assert seen["max_tokens"] >= 1500


@pytest.mark.asyncio
async def test_reflect_normalizes_unknown_action():
    async def fake(*a, **k):
        return '{"action":"explode","questions":["q1"],"reason":"x"}'

    with patch("athena.agents.controller.complete", side_effect=fake):
        out = await reflect("t", "f", ["q"], 1, 3, LLM)
    assert out["action"] == "continue"
