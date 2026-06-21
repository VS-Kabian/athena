import json
from ..gateway.llm import complete

DECOMP = ("You are a research planner. Break the topic into {n} focused, distinct sub-questions. "
          "Return ONLY a JSON array of strings. Topic: {topic}")
REFINE = ("Given the topic and findings so far, produce {n} NEW sub-questions that fill gaps or dig deeper. "
          "Return ONLY a JSON array of strings. Topic: {topic}\nFindings:\n{findings}")

def _fallback(topic: str, n: int) -> list[str]:
    angles = ["overview of", "key challenges in", "latest advances in", "tools and methods for", "criticism of"]
    return [f"{angles[i % len(angles)]} {topic}" for i in range(n)]

async def _ask(prompt: str, llm: dict, topic: str, n: int) -> list[str]:
    try:
        # longer timeout for reasoning ("pro"/R1-style) models; a slow or timed-out planner
        # call must NOT kill the whole run — fall back to heuristic sub-questions instead.
        raw = await complete(llm["provider"], llm["model"], [{"role": "user", "content": prompt}],
                             llm.get("api_key"), timeout=180)
    except Exception:
        return _fallback(topic, n)
    try:
        data = json.loads(raw[raw.index("["): raw.rindex("]")+1])
        qs = [str(x) for x in data][:n]
        return qs if qs else _fallback(topic, n)
    except Exception:
        return _fallback(topic, n)

async def decompose(topic: str, n: int, llm: dict) -> list[str]:
    return await _ask(DECOMP.format(n=n, topic=topic), llm, topic, n)

async def refine(topic: str, findings: str, n: int, llm: dict) -> list[str]:
    return await _ask(REFINE.format(n=n, topic=topic, findings=findings[:2000]), llm, topic, n)

EXPAND = ("You are a research planner refining an in-progress investigation. Given the topic, the "
          "sub-questions already being researched, and the findings so far, propose up to {n} NEW, "
          "DISTINCT sub-questions covering an IMPORTANT angle the existing ones do NOT yet address. "
          "Return ONLY a JSON array of strings — return [] if the existing sub-questions already cover "
          "the topic well. Never repeat or merely rephrase an existing sub-question.\n"
          "Topic: {topic}\nExisting sub-questions: {existing}\nFindings so far:\n{findings}")


async def expand_facets(topic: str, facets: list[str], findings: str, n: int = 2,
                        llm: dict | None = None) -> list[str]:
    """Adaptive planning: propose up to ``n`` NEW sub-questions (facets) that fill a gap the current
    set misses, given what's been found. Append-only by design — never returns an existing facet — so
    the coverage ledger's attribution stays stable. Returns [] when the model is absent / fails / the
    topic is already well covered."""
    if not llm:
        return []
    try:
        raw = await complete(
            llm["provider"], llm["model"],
            [{"role": "user", "content": EXPAND.format(n=n, topic=topic, existing=facets,
                                                       findings=(findings or "")[:1500])}],
            llm.get("api_key"), max_tokens=1500, timeout=120)
        data = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
    except Exception:
        return []
    existing = {f.strip().lower() for f in (facets or [])}
    out: list[str] = []
    for x in data:
        s = str(x).strip()
        low = s.lower()
        if s and low not in existing and low not in {o.lower() for o in out}:
            out.append(s)
    return out[:n]


ENTITIES = ("From the research topic, list the specific NAMED subjects to compare or analyze "
            "(e.g. product names, frameworks, tools, methods, companies). Return ONLY a JSON array "
            "of short strings (max 8). If none are explicitly named, return []. Topic: {topic}")

async def extract_entities(topic: str, llm: dict) -> list[str]:
    try:
        raw = await complete(llm["provider"], llm["model"],
                             [{"role": "user", "content": ENTITIES.format(topic=topic)}],
                             llm.get("api_key"), max_tokens=1500, timeout=120)
        data = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
        return [str(x).strip() for x in data if str(x).strip()][:8]
    except Exception:
        return []
