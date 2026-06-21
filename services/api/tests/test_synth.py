import pytest
from unittest.mock import patch
from athena.agents.synthesizer import synthesize, strip_invalid_citations


def test_strip_invalid_citations_removes_out_of_range_markers():
    # R5: fabricated/out-of-range [n] (n==0 or n>N) are stripped; valid citations are kept
    assert strip_invalid_citations("see [3] and [45] and [0].", 10) == "see [3] and  and ."
    assert strip_invalid_citations("all valid [1] [2].", 2) == "all valid [1] [2]."
    assert strip_invalid_citations("no markers here.", 5) == "no markers here."

@pytest.mark.asyncio
async def test_synthesize_from_evidence_includes_sources_and_returns_order():
    evidence = [
        {"url": "https://a.com", "text": "LangChain is modular and flexible.", "score": 0.9},
        {"url": "https://b.com", "text": "LlamaIndex focuses on data indexing.", "score": 0.8},
    ]
    async def fake(*a, **k): return "## Findings\nLangChain is modular [1]. LlamaIndex indexes data [2]."
    with patch("athena.agents.synthesizer.complete", side_effect=fake):
        md, order, src_texts = await synthesize("topic", evidence, {"provider": "groq", "model": "m", "api_key": "k"})
    assert "## Findings" in md and "https://a.com" in md
    assert order == ["https://a.com", "https://b.com"]
    assert "LangChain is modular" in src_texts["https://a.com"]


@pytest.mark.asyncio
async def test_synthesize_trims_evidence_to_budget():
    # 50 long sources; the char budget must cap how many reach the model
    evidence = [{"url": f"https://s{i}.com", "text": "x" * 2000, "score": 0.9} for i in range(50)]
    async def fake(*a, **k): return "report [1]"
    with patch("athena.agents.synthesizer.complete", side_effect=fake):
        md, order, src = await synthesize("t", evidence, {"provider": "groq", "model": "m", "api_key": "k"})
    assert 0 < len(order) < 50  # trimmed by budget, not all 50

@pytest.mark.asyncio
async def test_synthesize_retries_smaller_on_length_error():
    evidence = [{"url": f"https://s{i}.com", "text": "x" * 2000, "score": 0.9} for i in range(12)]
    calls = {"n": 0}
    async def fake(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("GroqException - Please reduce the length of the messages or completion")
        return "report [1]"
    with patch("athena.agents.synthesizer.complete", side_effect=fake):
        md, order, src = await synthesize("t", evidence, {"provider": "groq", "model": "m", "api_key": "k"})
    assert calls["n"] >= 2
    assert md.startswith("# Research Report")


@pytest.mark.asyncio
async def test_synthesize_retries_smaller_on_timeout():
    evidence = [{"url": f"https://s{i}.com", "text": "x" * 2000, "score": 0.9} for i in range(10)]
    calls = {"n": 0}
    async def fake(*a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("litellm.Timeout: the model took too long / timed out")
        return "report [1]"
    with patch("athena.agents.synthesizer.complete", side_effect=fake):
        md, order, src = await synthesize("t", evidence, {"provider": "groq", "model": "m", "api_key": "k"})
    assert calls["n"] >= 2 and md.startswith("# Research Report")


@pytest.mark.asyncio
async def test_synthesize_retries_on_empty_body_with_more_tokens():
    evidence = [{"url": "https://a.com", "text": "content about agents", "score": 0.9}]
    calls = {"n": 0, "tokens": []}
    async def fake(*a, **k):
        calls["n"] += 1
        calls["tokens"].append(k.get("max_tokens"))
        if calls["n"] == 1:
            return "   "  # empty (reasoning model spent its budget on reasoning)
        return "## Findings\nReal report content [1]."
    with patch("athena.agents.synthesizer.complete", side_effect=fake):
        md, order, src = await synthesize("t", evidence, {"provider": "deepseek", "model": "deepseek-v4-pro", "api_key": "k"})
    assert calls["n"] >= 2
    assert "Real report content" in md
    assert calls["tokens"][1] > calls["tokens"][0]  # escalated output tokens on the retry


@pytest.mark.asyncio
async def test_synthesize_retries_when_truncated_at_token_cap():
    # a non-empty body cut off at max_tokens (finish_reason=="length") must NOT be shipped as-is —
    # it should retry with a bigger output budget so the full report is produced.
    calls = {"n": 0, "tokens": []}
    async def fake_stream(provider, model, messages, api_key=None, **k):
        calls["n"] += 1; calls["tokens"].append(k.get("max_tokens"))
        if calls["n"] == 1:
            return "## Findings\npartial report that got cut off [1]", {"total_tokens": 200, "finish_reason": "length"}
        return "## Findings\ncomplete report [1].", {"total_tokens": 400, "finish_reason": "stop"}
    async def od(t): pass
    with patch("athena.agents.synthesizer.stream_complete", side_effect=fake_stream):
        md, order, src = await synthesize("t", [{"url": "https://a.com", "text": "x", "score": 0.9}],
                                          {"provider": "g", "model": "m", "api_key": "k"}, on_delta=od)
    assert calls["n"] >= 2                          # truncation triggered a retry
    assert calls["tokens"][1] > calls["tokens"][0]  # ...with a larger output budget
    assert "complete report" in md and "got cut off" not in md


@pytest.mark.asyncio
async def test_synthesize_falls_back_to_complete_when_streaming_errors():
    async def boom_stream(*a, **k): raise RuntimeError("stream_options unsupported by provider")
    async def fake_complete(*a, **k): return "## Findings\nfallback report [1]"
    async def od(t): pass
    with patch("athena.agents.synthesizer.stream_complete", side_effect=boom_stream), \
         patch("athena.agents.synthesizer.complete", side_effect=fake_complete):
        md, order, src = await synthesize("t", [{"url": "https://a.com", "text": "x", "score": 0.9}],
                                          {"provider": "g", "model": "m", "api_key": "k"}, on_delta=od)
    assert "fallback report" in md   # proven non-stream path kept synthesis alive


@pytest.mark.asyncio
async def test_synthesize_streams_and_reports_usage_when_on_delta_given():
    deltas, usages = [], []
    async def fake_stream(provider, model, messages, api_key=None, **k):
        od = k.get("on_delta")
        if od:
            await od("partial "); await od("report [1]")
        return "## Findings\nfull report [1]", {"total_tokens": 100}
    async def on_delta(t): deltas.append(t)
    with patch("athena.agents.synthesizer.stream_complete", side_effect=fake_stream):
        md, order, src = await synthesize("t", [{"url": "https://a.com", "text": "x", "score": 0.9}],
                                          {"provider": "g", "model": "m", "api_key": "k"},
                                          on_delta=on_delta, on_usage=lambda u: usages.append(u))
    assert "".join(deltas) == "partial report [1]"          # streamed token-by-token
    assert usages and usages[0]["total_tokens"] == 100      # usage surfaced
    assert md.startswith("# Research Report")


@pytest.mark.asyncio
async def test_evidence_is_delimited_as_untrusted_for_injection_safety():
    captured = {}
    async def fake(provider, model, messages, api_key=None, **k):
        captured["sys"] = messages[0]["content"]
        captured["user"] = messages[1]["content"]
        return "## Findings\nReport [1]."
    ev = [{"url": "https://a.com", "text": "scraped page text", "score": 0.9}]
    with patch("athena.agents.synthesizer.complete", side_effect=fake):
        await synthesize("t", ev, {"provider": "g", "model": "m", "api_key": "k"})
    assert "UNTRUSTED EVIDENCE" in captured["user"]   # evidence is fenced
    assert "untrusted" in captured["sys"].lower()      # system prompt warns against following it


@pytest.mark.asyncio
async def test_synthesize_empty_body_falls_back_to_note():
    evidence = [{"url": "https://a.com", "text": "x", "score": 0.9}]
    async def fake(*a, **k): return ""  # always empty
    with patch("athena.agents.synthesizer.complete", side_effect=fake):
        md, order, src = await synthesize("t", evidence, {"provider": "deepseek", "model": "m", "api_key": "k"})
    assert "empty report body" in md.lower()
