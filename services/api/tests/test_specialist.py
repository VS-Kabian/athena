import pytest, respx, httpx
from athena.search.specialist import arxiv_search, github_search

ARXIV_XML = """<?xml version="1.0"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2312.10997v1</id>
    <title>Retrieval-Augmented Generation for LLMs: A Survey</title>
    <summary>This paper surveys retrieval augmented generation methods and frameworks in detail.</summary>
  </entry>
</feed>"""

@pytest.mark.asyncio
@respx.mock
async def test_arxiv_parses_abstract():
    respx.get("https://export.arxiv.org/api/query").mock(return_value=httpx.Response(200, text=ARXIV_XML))
    res = await arxiv_search("rag", k=3)
    assert res and res[0]["source_type"] == "paper"
    assert "survey" in res[0]["content"].lower()
    assert res[0]["url"].startswith("http://arxiv.org/abs/")

@pytest.mark.asyncio
@respx.mock
async def test_github_parses_repo_and_readme():
    respx.get("https://api.github.com/search/repositories").mock(return_value=httpx.Response(200, json={
        "items": [{"full_name": "run-llama/llama_index", "html_url": "https://github.com/run-llama/llama_index",
                   "description": "LlamaIndex is a data framework", "stargazers_count": 30000}]}))
    respx.get("https://api.github.com/repos/run-llama/llama_index/readme").mock(
        return_value=httpx.Response(200, text="LlamaIndex README: a data framework for LLM applications."))
    res = await github_search("llamaindex", k=2)
    assert res and res[0]["source_type"] == "github"
    assert "data framework" in res[0]["content"].lower()
    assert res[0]["url"] == "https://github.com/run-llama/llama_index"
