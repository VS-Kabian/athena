from athena.tokens import count_tokens
from athena.agents.synthesizer import _build_block


def test_count_tokens_empty_is_zero():
    assert count_tokens("") == 0
    assert count_tokens(None) == 0


def test_count_tokens_scales_with_length():
    short = count_tokens("hello world")
    long = count_tokens("hello world " * 200)
    assert short > 0
    assert long > short


def test_count_tokens_roughly_proportional_to_words():
    # a token spans at most ~1 word, so the estimate is at least the word count
    text = " ".join(["word"] * 100)
    assert count_tokens(text) >= 50


def test_build_block_respects_token_budget():
    order = [f"https://s{i}.com" for i in range(20)]
    by_url = {u: ["x " * 400] for u in order}  # ~800 chars each, token-dense
    # a tight token budget must trim more sources than a generous one, even with a huge char budget
    _, tight = _build_block(order, by_url, max_chars=10_000_000, max_tokens=300)
    _, loose = _build_block(order, by_url, max_chars=10_000_000, max_tokens=100_000)
    assert 0 < len(tight) < len(loose)


def test_build_block_always_keeps_at_least_one_source():
    order = ["https://big.com"]
    by_url = {"https://big.com": ["x" * 50_000]}
    _, included = _build_block(order, by_url, max_chars=10, max_tokens=1)
    assert included == ["https://big.com"]  # never drop the only source
