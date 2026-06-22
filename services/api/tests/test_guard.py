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


def test_corroboration_excludes_same_domain_as_cited():
    # P2-8: the only OTHER supporter is a mirror on the cited claim's own domain -> NOT independent
    md = "## F\nA widely repeated fact [1].\n\n## Sources\n1. a\n2. b"
    urls = ["https://site.com/x", "https://site.com/y"]      # cited + same-domain mirror
    with patch("athena.agents.guard.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.agents.guard.embed_passages", side_effect=lambda chunks: [[1.0, 0.0]]):
        r = factcheck(md, ["primary", "mirror"], source_urls=urls)
    assert r["consensus"] == 0.0                              # same-domain mirror doesn't corroborate
    assert any("widely repeated fact" in s for s in r["single_source"])


def test_corroboration_counts_distinct_domain():
    md = "## F\nA widely repeated fact [1].\n\n## Sources\n1. a\n2. b"
    urls = ["https://site.com/x", "https://other-org.com/y"]  # cited + an INDEPENDENT domain
    with patch("athena.agents.guard.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.agents.guard.embed_passages", side_effect=lambda chunks: [[1.0, 0.0]]):
        r = factcheck(md, ["primary", "independent"], source_urls=urls)
    assert r["consensus"] == 1.0                              # a distinct domain genuinely corroborates


def test_factcheck_grounds_against_supplied_evidence_chunks_not_raw_source():
    # P1-2: when given the EXACT chunks shown to the writer, factcheck embeds THOSE — not a re-chunk of the
    # raw page — so a claim whose supporting passage sits past the first 6000 chars is checked correctly.
    md = "## Findings\nThe model reached state of the art on the benchmark [1].\n\n## Sources\n1. a"
    raw = "filler text. " * 1000                                      # supporting passage NOT in first 6000 chars
    shown = ["The model reached state of the art on the benchmark."]   # the chunk actually shown to the writer
    seen: list[str] = []

    def spy_embed_passages(chunks):
        seen.extend(chunks)
        return [[1.0, 0.0] for _ in chunks]

    with patch("athena.agents.guard.embed_query", return_value=[1.0, 0.0]), \
         patch("athena.agents.guard.embed_passages", side_effect=spy_embed_passages):
        r = factcheck(md, [raw], evidence_chunks=[shown])
    assert any("state of the art" in p for p in seen)   # the shown chunk WAS embedded
    assert not any("filler" in p for p in seen)          # the raw page was NOT re-chunked
    assert r["risk"] == 0.0                               # and the claim is grounded against the shown chunk
