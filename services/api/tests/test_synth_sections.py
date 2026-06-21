"""Section-by-section synthesis (Upgrade 2): outline -> per-section retrieval -> grounded section,
with globally-numbered citations and graceful fallback to the single-pass writer."""
import pytest
from unittest.mock import patch, AsyncMock

from athena.agents import synthesizer
from athena.agents.synthesizer import synthesize_sections

LLM = {"provider": "g", "model": "m", "api_key": "k"}


def _ev(n):
    return [{"url": f"https://s{i}.com", "text": f"evidence text {i}", "score": 1.0 - i * 0.01} for i in range(n)]


@pytest.mark.asyncio
async def test_outline_drives_sections_with_global_sources():
    captured = []
    async def fake_complete(provider, model, messages, api_key, **kw):
        captured.append(messages[-1]["content"])
        return "Body grounded in [1] and [3]."
    with patch.object(synthesizer, "_outline", AsyncMock(return_value=["Overview", "Comparison"])), \
         patch.object(synthesizer, "rerank", return_value=[]), \
         patch.object(synthesizer, "complete", side_effect=fake_complete):
        md, order, src = await synthesize_sections("topic", _ev(5), LLM, facets=["f"])
    assert "## Overview" in md and "## Comparison" in md
    assert "## Sources" in md and len(order) == 5
    assert len(captured) == 2                      # one write call per section


@pytest.mark.asyncio
async def test_per_section_evidence_is_section_targeted_with_global_numbers():
    captured = []
    async def fake_complete(provider, model, messages, api_key, **kw):
        captured.append(messages[-1]["content"])
        return "Section body [1]."
    sel = {"Sec A": ["https://s0.com"], "Sec B": ["https://s2.com"]}
    with patch.object(synthesizer, "_outline", AsyncMock(return_value=["Sec A", "Sec B"])), \
         patch.object(synthesizer, "_select_all", return_value=sel), \
         patch.object(synthesizer, "complete", side_effect=fake_complete):
        await synthesize_sections("topic", _ev(5), LLM)
    a, b = captured[0], captured[1]
    assert "https://s0.com" in a and "https://s2.com" not in a   # Sec A sees only its evidence
    assert "https://s2.com" in b and "https://s0.com" not in b
    assert "[1]" in a and "[3]" in b                             # global numbering: s0=[1], s2=[3]


@pytest.mark.asyncio
async def test_falls_back_to_single_pass_on_empty_outline():
    with patch.object(synthesizer, "_outline", AsyncMock(return_value=[])), \
         patch.object(synthesizer, "synthesize", AsyncMock(return_value=("# Single", ["u"], {"u": "t"}))) as sp:
        md, order, src = await synthesize_sections("topic", _ev(5), LLM)
    sp.assert_awaited_once()
    assert md == "# Single"


@pytest.mark.asyncio
async def test_falls_back_to_single_pass_when_too_few_sources():
    with patch.object(synthesizer, "synthesize", AsyncMock(return_value=("# Single", ["u"], {"u": "t"}))) as sp:
        md, _, _ = await synthesize_sections("topic", _ev(2), LLM)   # < 4 sources
    sp.assert_awaited_once()
    assert md == "# Single"


@pytest.mark.asyncio
async def test_section_failure_inserts_placeholder_not_crash():
    async def boom(*a, **k):
        raise RuntimeError("model down")
    with patch.object(synthesizer, "_outline", AsyncMock(return_value=["A", "B"])), \
         patch.object(synthesizer, "rerank", return_value=[]), \
         patch.object(synthesizer, "complete", side_effect=boom):
        md, order, src = await synthesize_sections("topic", _ev(5), LLM)
    assert "Insufficient evidence" in md and "## A" in md and "## B" in md
    assert len(order) == 5
