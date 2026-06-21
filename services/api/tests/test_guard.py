from unittest.mock import patch
from athena.agents.guard import factcheck

def test_supported_claim_low_risk():
    md = "## Findings\nLangChain is a modular framework for building LLM apps [1].\n\n## Sources\n1. https://a.com"
    with patch("athena.agents.guard.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.agents.guard.embed_passages", return_value=[[1.0, 0.0]]):
        r = factcheck(md, ["LangChain is a modular framework for building applications"])
    assert r["risk"] == 0.0

def test_unsupported_claim_flagged():
    md = "## Findings\nHaystack reaches exactly 700 QPS and 90 percent accuracy [1].\n\n## Sources\n1. https://a.com"
    with patch("athena.agents.guard.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.agents.guard.embed_passages", return_value=[[0.0, 1.0]]):
        r = factcheck(md, ["Haystack is a search framework for question answering"])
    assert r["unsupported"] >= 1 and r["risk"] > 0.0


def test_uncited_claim_is_unsupported_not_matched_to_any_source():
    # a factual sentence with NO [n] must NOT be validated by resembling some random source
    md = "## Findings\nThe market grew four hundred percent in the year according to no one.\n\n## Sources\n1. https://a.com"
    with patch("athena.agents.guard.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.agents.guard.embed_passages", return_value=[[1.0, 0.0]]):
        r = factcheck(md, ["totally unrelated source text about cooking pasta"])
    assert r["unsupported"] >= 1 and r["risk"] > 0.0


def test_out_of_range_citation_is_unsupported():
    md = "## Findings\nThis claim cites a source that is not in the list at all [9].\n\n## Sources\n1. https://a.com"
    with patch("athena.agents.guard.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.agents.guard.embed_passages", return_value=[[1.0, 0.0]]):
        r = factcheck(md, ["only one source is present here"])
    assert r["unsupported"] >= 1


def test_single_source_claim_flagged_as_uncorroborated():
    md = "## Findings\nThe framework is modular and fast [1].\n\n## Sources\n1. a\n2. b\n3. c"
    calls = {"n": 0}

    def emb_p(chunks):
        calls["n"] += 1
        return [[1.0, 0.0]] if calls["n"] == 1 else [[0.0, 1.0]]   # only source 1 aligns

    with patch("athena.agents.guard.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.agents.guard.embed_passages", side_effect=emb_p):
        r = factcheck(md, ["aligned source text", "other", "another"])
    assert r["risk"] == 0.0                                       # supported by its cited source
    assert any("modular and fast" in s for s in r["single_source"])  # but only one source backs it
    assert r["consensus"] == 0.0


def test_multi_source_claim_is_corroborated():
    md = "## Findings\nA widely agreed fact here [1].\n\n## Sources\n1. a\n2. b"

    def emb_p(chunks):
        return [[1.0, 0.0]]   # every source aligns -> corroborated

    with patch("athena.agents.guard.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.agents.guard.embed_passages", side_effect=emb_p):
        r = factcheck(md, ["src a", "src b"])
    assert r["consensus"] == 1.0 and r["single_source"] == []
