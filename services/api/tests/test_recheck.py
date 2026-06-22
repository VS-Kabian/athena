"""Reference-free re-verification (P1-4): re-check the highest-risk claims against FRESH independent
sources (not the cited source) and flag any a fresh source refutes — the "cited-but-wrong" failure that
single-source entailment can't catch. Dependency-injected search/fetch/entail keep this deterministic."""
import pytest

from athena.agents.recheck import recheck_claims


class _Hit:
    def __init__(self, url):
        self.url = url


LLM = {"provider": "g", "model": "m", "api_key": "k"}


@pytest.mark.asyncio
async def test_flags_claim_refuted_by_fresh_source():
    verdicts = [{"claim": "X reached 900 QPS [1].", "verdict": "nei"},
                {"claim": "Y is fully supported [2].", "verdict": "supported"}]

    async def search(q):
        return [_Hit("https://fresh.com")]

    async def fetch(urls):
        return {"https://fresh.com": "an independent source that contradicts the claim"}

    async def entail(md, sources, llm):
        return {"engine": "entailment", "refuted": 1, "nei": 0, "supported": 0}

    out = await recheck_claims(verdicts, "topic", LLM, search=search, fetch=fetch, entail=entail, k=2)
    assert any(r["refuted_by_fresh"] for r in out)                 # the NEI claim is flagged cited-but-wrong
    assert all("Y is fully supported" not in r["claim"] for r in out)   # supported claims are not re-checked


@pytest.mark.asyncio
async def test_no_flag_when_fresh_source_supports():
    verdicts = [{"claim": "X is true [1].", "verdict": "nei"}]

    async def search(q):
        return [_Hit("https://fresh.com")]

    async def fetch(urls):
        return {"https://fresh.com": "an independent source that supports the claim"}

    async def entail(md, sources, llm):
        return {"engine": "entailment", "refuted": 0, "nei": 0, "supported": 1}

    out = await recheck_claims(verdicts, "topic", LLM, search=search, fetch=fetch, entail=entail)
    assert out and not any(r["refuted_by_fresh"] for r in out)


@pytest.mark.asyncio
async def test_best_effort_when_no_fresh_sources():
    verdicts = [{"claim": "X [1].", "verdict": "refuted"}]

    async def search(q):
        return []                                                  # fresh search found nothing

    async def fetch(urls):
        return {}

    async def entail(md, sources, llm):
        return {"engine": "entailment", "refuted": 0}

    out = await recheck_claims(verdicts, "t", LLM, search=search, fetch=fetch, entail=entail)
    assert out == []                                               # nothing to refute against -> no crash, no flags


@pytest.mark.asyncio
async def test_skips_when_no_llm_or_no_verdicts():
    async def search(q):
        return [_Hit("https://x.com")]

    async def fetch(urls):
        return {"https://x.com": "text"}

    async def entail(md, sources, llm):
        return {"engine": "entailment", "refuted": 1}

    assert await recheck_claims([], "t", LLM, search=search, fetch=fetch, entail=entail) == []
    assert await recheck_claims([{"claim": "a [1].", "verdict": "refuted"}], "t", None,
                                search=search, fetch=fetch, entail=entail) == []
