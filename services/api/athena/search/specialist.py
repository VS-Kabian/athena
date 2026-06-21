import asyncio

import httpx
from defusedxml.ElementTree import fromstring as _xml_fromstring

ARXIV_API = "https://export.arxiv.org/api/query"
GITHUB_API = "https://api.github.com"

async def arxiv_search(query: str, k: int = 5) -> list[dict]:
    params = {"search_query": f"all:{query}", "start": 0, "max_results": k, "sortBy": "relevance"}
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True) as c:
            r = await c.get(ARXIV_API, params=params)
            r.raise_for_status()
            root = _xml_fromstring(r.text)
    except Exception:
        return []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    out = []
    for entry in root.findall("a:entry", ns):
        title = (entry.findtext("a:title", default="", namespaces=ns) or "").strip().replace("\n", " ")
        summary = (entry.findtext("a:summary", default="", namespaces=ns) or "").strip()
        url = (entry.findtext("a:id", default="", namespaces=ns) or "").strip()
        if url and title and summary:
            out.append({"url": url, "title": title, "snippet": summary[:300],
                        "content": f"{title}\n\n{summary}", "source_type": "paper"})
    return out

async def github_search(query: str, k: int = 4) -> list[dict]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "ATHENA-Research/1.0"}
    try:
        async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=headers) as c:
            r = await c.get(f"{GITHUB_API}/search/repositories",
                            params={"q": query, "sort": "stars", "per_page": k})
            r.raise_for_status()
            repos = r.json().get("items", [])
    except Exception:
        return []
    out = []
    selected = repos[:k]
    raw_headers = {"Accept": "application/vnd.github.raw+json", "User-Agent": "ATHENA-Research/1.0"}
    async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=raw_headers) as c:
        async def _readme(full: str) -> str:
            try:
                rr = await c.get(f"{GITHUB_API}/repos/{full}/readme")
                if rr.status_code == 200:
                    return rr.text[:4000]
            except Exception:
                pass
            return ""

        # fetch all READMEs concurrently instead of one serial round-trip per repo (N+1 latency)
        readmes = await asyncio.gather(
            *[_readme(repo.get("full_name") or "") for repo in selected],
            return_exceptions=True)
        for repo, readme in zip(selected, readmes):
            full = repo.get("full_name") or ""
            url = repo.get("html_url") or ""
            desc = repo.get("description") or ""
            stars = repo.get("stargazers_count", 0)
            if isinstance(readme, BaseException):
                readme = ""
            if not url:
                continue
            out.append({"url": url, "title": f"{full} (GitHub, {stars}★)",
                        "snippet": desc[:300], "content": f"{full} - {desc}\n\n{readme}",
                        "source_type": "github"})
    return out
