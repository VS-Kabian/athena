"""NLI-as-decision + honest fallback (P0-3): when the entailment judge did NOT actually run (cosine-only
fallback), the run is flagged reduced-assurance and its risk is floored so it can't be presented as a
confident '<10%' pass. When the judge ran, the run is full-assurance and unfloored."""
import json
from contextlib import ExitStack

import pytest
from unittest.mock import patch, AsyncMock

from athena.agents.quality import aggregate_risk
from athena.agents.graph import run_research
from athena.search.base import SearchHit

REPORT = "# Report\n\nThis is claim number one about the chosen topic [1].\n\n## Sources\n1. https://a.com"
SRC = {"https://a.com": "Source text that clearly supports claim number one about the chosen topic."}


# ── unit: the degraded floor is honest uncertainty — it only ever RAISES risk ──
def test_degraded_floor_lifts_an_overconfident_cosine_zero():
    full = aggregate_risk(refuted=0, nei=0, total_claims=5)["risk"]
    degraded = aggregate_risk(refuted=0, nei=0, total_claims=5, degraded=True)["risk"]
    assert full == 0.0
    assert degraded >= 0.10            # cosine-only -> cannot claim a confident <10% pass


def test_degraded_floor_never_lowers_a_real_risk():
    r = aggregate_risk(refuted=4, nei=0, total_claims=5, degraded=True)["risk"]
    assert r >= 0.8                    # a genuinely high risk is unchanged (max, not min — never flatters)


def test_full_assurance_is_not_floored():
    assert aggregate_risk(refuted=0, nei=0, total_claims=5, degraded=False)["risk"] == 0.0


# ── integration: engine -> assurance, end to end (mirrors test_trust_wiring's proven structure) ──
def _patch_map(events, entail_complete):
    async def fake_publish(run_id, ev):
        events.append(ev)
    hits = [SearchHit("https://a.com", "A", "s", 0, "ddg")]
    G = "athena.agents.graph."
    return {
        G + "bus.publish": patch(G + "bus.publish", side_effect=fake_publish),
        G + "bus.is_cancelled": patch(G + "bus.is_cancelled", return_value=False),
        G + "arxiv_search": patch(G + "arxiv_search", AsyncMock(return_value=[])),
        G + "github_search": patch(G + "github_search", AsyncMock(return_value=[])),
        G + "filter_by_relevance": patch(G + "filter_by_relevance", side_effect=lambda t, h: h),
        G + "decompose": patch(G + "decompose", AsyncMock(return_value=["q1"])),
        G + "extract_entities": patch(G + "extract_entities", AsyncMock(return_value=["EntityA"])),
        G + "multi_search": patch(G + "multi_search", AsyncMock(return_value=hits)),
        G + "persist_sources": patch(G + "persist_sources", AsyncMock()),
        G + "recall": patch(G + "recall", AsyncMock(return_value=[])),
        G + "remember": patch(G + "remember", AsyncMock()),
        G + "select_sources": patch(G + "select_sources", side_effect=lambda a, n=20, entities=None: list(a.values())),
        G + "fetch_many": patch(G + "fetch_many", AsyncMock(return_value={"https://a.com": "content"})),
        G + "assemble_content": patch(G + "assemble_content", side_effect=lambda s, d: {"https://a.com": "content"}),
        G + "build_evidence": patch(G + "build_evidence", return_value=[{"url": "https://a.com", "text": "content", "score": 0.9}]),
        G + "synthesize_sections": patch(G + "synthesize_sections", AsyncMock(return_value=(REPORT, ["https://a.com"], SRC))),
        G + "factcheck": patch(G + "factcheck", return_value={"risk": 0.0, "total": 1, "unsupported": 0,
                                                              "flagged": [], "single_source": [], "consensus": 1.0}),
        G + "select_span": patch(G + "select_span", side_effect=lambda t, x, max_chars=400: x),
        G + "check_urls": patch(G + "check_urls", AsyncMock(return_value={"https://a.com": {"status": "live", "code": 200}})),
        G + "persist_claims": patch(G + "persist_claims", AsyncMock()),
        G + "persist_report": patch(G + "persist_report", AsyncMock()),
        "athena.agents.entail.complete": patch("athena.agents.entail.complete", side_effect=entail_complete),
    }


@pytest.mark.asyncio
async def test_entailment_run_is_full_assurance():
    events = []

    async def good(provider, model, messages, api_key, **kw):
        return json.dumps([{"n": 1, "verdict": "supported", "confidence": 0.9, "conflict": False}])

    with ExitStack() as stack:
        for p in _patch_map(events, good).values():
            stack.enter_context(p)
        await run_research("r", "t", rounds=1, llm={"provider": "g", "model": "m", "api_key": "k"},
                           providers=[], mode="broadcast")
    ent = next(e for e in events if e["type"] == "entail")["data"]
    assert ent["engine"] == "entailment" and ent["assurance"] == "full"


@pytest.mark.asyncio
async def test_cosine_fallback_run_is_reduced_assurance_and_not_confident():
    events = []

    async def fail(provider, model, messages, api_key, **kw):
        raise RuntimeError("model unavailable")     # judge can't run -> cosine fallback (twice incl. retry)

    with ExitStack() as stack:
        for p in _patch_map(events, fail).values():
            stack.enter_context(p)
        await run_research("r", "t", rounds=1, llm={"provider": "g", "model": "m", "api_key": "k"},
                           providers=[], mode="broadcast")
    ent = next(e for e in events if e["type"] == "entail")["data"]
    q = next(e for e in events if e["type"] == "quality")["data"]
    assert ent["engine"] != "entailment" and ent["assurance"] == "reduced"
    assert q["assurance"] == "reduced"
    assert q["hallucination_risk"] >= 0.10          # cosine-only -> floored, not a confident <10% pass
