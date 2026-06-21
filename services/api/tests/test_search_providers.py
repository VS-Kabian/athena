import pytest, respx, httpx
from athena.search.providers import SearxngProvider, SerperProvider


@pytest.mark.asyncio
@respx.mock
async def test_searxng_parses_json():
    respx.get("http://localhost:8080/search").mock(return_value=httpx.Response(200, json={
        "results": [{"url": "https://a.com", "title": "A", "content": "snip"}]}))
    hits = await SearxngProvider().search("q", k=5)
    assert hits[0].url == "https://a.com" and hits[0].provider == "searxng" and hits[0].rank == 0


@pytest.mark.asyncio
@respx.mock
async def test_serper_parses_organic():
    respx.post("https://google.serper.dev/search").mock(return_value=httpx.Response(200, json={
        "organic": [{"link": "https://b.com", "title": "B", "snippet": "s"}]}))
    hits = await SerperProvider(api_key="k").search("q", k=5)
    assert hits[0].url == "https://b.com" and hits[0].provider == "serper"
