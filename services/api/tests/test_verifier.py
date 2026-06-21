import pytest
from unittest.mock import patch
from athena.agents.verifier import verify_report

MD = ("# Research Report: x\n\n## Findings\n"
      "The sky is green [1]. Water boils at 100C [2].\n\n## Sources\n\n1. a\n2. b\n")
SRC = ["The sky is blue on a clear day.", "Water boils at 100 degrees Celsius at sea level."]
LLM = {"provider": "groq", "model": "verify-m", "api_key": "k"}


@pytest.mark.asyncio
async def test_corrects_contradicted_and_flags_weak():
    calls = {"n": 0}

    async def fake(*a, **k):
        calls["n"] += 1
        return ('[{"n":1,"verdict":"contradicted","correction":"The sky is blue [1]."},'
                ' {"n":2,"verdict":"supported","correction":""}]')

    with patch("athena.agents.verifier.complete", side_effect=fake):
        md, contested = await verify_report(MD, SRC, LLM)
    assert "The sky is blue [1]." in md and "sky is green" not in md
    assert calls["n"] == 1                      # one batched call, not per-claim
    assert any("corrected" in c.lower() for c in contested)


@pytest.mark.asyncio
async def test_weak_is_flagged_not_rewritten():
    async def fake(*a, **k):
        return '[{"n":1,"verdict":"weak","correction":""},{"n":2,"verdict":"supported","correction":""}]'

    with patch("athena.agents.verifier.complete", side_effect=fake):
        md, contested = await verify_report(MD, SRC, LLM)
    assert "sky is green" in md                 # weak claims are not rewritten
    assert len(contested) == 1


@pytest.mark.asyncio
async def test_verifier_error_returns_original_unchanged():
    async def boom(*a, **k):
        raise RuntimeError("timeout")

    with patch("athena.agents.verifier.complete", side_effect=boom):
        md, contested = await verify_report(MD, SRC, LLM)
    assert md == MD and contested == []


@pytest.mark.asyncio
async def test_long_report_is_verified_in_batches_not_one_giant_call():
    # 45 cited sentences -> must chunk (20/batch => 3 calls) instead of one truncation-prone call
    import json
    lines = "\n".join(f"Claim number {i} is stated here [1]." for i in range(45))
    md = f"# R\n\n## Findings\n{lines}\n\n## Sources\n\n1. a\n"
    calls = {"n": 0}
    async def fake(provider, model, messages, api_key, **k):
        calls["n"] += 1
        batch = json.loads(messages[1]["content"])
        return json.dumps([{"n": it["n"], "verdict": "supported", "correction": ""} for it in batch])
    with patch("athena.agents.verifier.complete", side_effect=fake):
        out_md, contested = await verify_report(md, ["alpha source text"], LLM)
    assert calls["n"] == 3                       # ceil(45 / 20) batches
    assert out_md == md and contested == []      # all supported -> nothing changed


@pytest.mark.asyncio
async def test_verifier_ignores_out_of_range_n():
    # a verdict whose n is outside this batch's range must be dropped, never applied to the wrong sentence
    async def fake(*a, **k):
        return '[{"n":99,"verdict":"contradicted","correction":"BOGUS REWRITE [1]."}]'
    with patch("athena.agents.verifier.complete", side_effect=fake):
        md, contested = await verify_report(MD, SRC, LLM)
    assert md == MD and contested == []          # n=99 ∉ [1,2] -> ignored, report untouched


@pytest.mark.asyncio
async def test_no_cited_sentences_is_noop():
    async def fake(*a, **k):
        return "[]"

    with patch("athena.agents.verifier.complete", side_effect=fake):
        md, contested = await verify_report("# r\n\nNo citations here.\n", [], LLM)
    assert contested == []
