import httpx
from .base import SearchHit
from ..config import settings


class SearxngProvider:
    name = "searxng"; needs_key = False
    async def search(self, query: str, k: int = 10) -> list[SearchHit]:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"{settings.searxng_url}/search",
                            params={"q": query, "format": "json"})
            r.raise_for_status()
            out = r.json().get("results", [])[:k]
        return [SearchHit(url=x.get("url",""), title=x.get("title",""),
                          snippet=x.get("content",""), rank=i, provider=self.name)
                for i, x in enumerate(out) if x.get("url")]


class DuckDuckGoProvider:
    name = "ddg"; needs_key = False
    async def search(self, query: str, k: int = 10) -> list[SearchHit]:
        import anyio
        from ddgs import DDGS
        def _sync():
            with DDGS() as d:
                return list(d.text(query, max_results=k))
        rows = await anyio.to_thread.run_sync(_sync)
        return [SearchHit(url=x.get("href",""), title=x.get("title",""),
                          snippet=x.get("body",""), rank=i, provider=self.name)
                for i, x in enumerate(rows) if x.get("href")]


class TavilyProvider:
    name = "tavily"; needs_key = True
    def __init__(self, api_key: str): self.api_key = api_key
    async def search(self, query: str, k: int = 10) -> list[SearchHit]:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.post("https://api.tavily.com/search",
                json={"api_key": self.api_key, "query": query, "max_results": k})
            r.raise_for_status()
            out = r.json().get("results", [])
        return [SearchHit(url=x.get("url",""), title=x.get("title",""),
                          snippet=x.get("content",""), rank=i, provider=self.name)
                for i, x in enumerate(out) if x.get("url")]


class SerperProvider:
    name = "serper"; needs_key = True
    def __init__(self, api_key: str): self.api_key = api_key
    async def search(self, query: str, k: int = 10) -> list[SearchHit]:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post("https://google.serper.dev/search",
                headers={"X-API-KEY": self.api_key}, json={"q": query, "num": k})
            r.raise_for_status()
            out = r.json().get("organic", [])
        return [SearchHit(url=x.get("link",""), title=x.get("title",""),
                          snippet=x.get("snippet",""), rank=i, provider=self.name)
                for i, x in enumerate(out) if x.get("link")]
