import json
from ..gateway.llm import complete

RACE_SYS = ("You are a strict research-report grader. Score the report from 0-10 on EACH of: "
            "comprehensiveness, depth, instruction_following, readability. Be harsh. Return ONLY a JSON "
            "object: {\"comprehensiveness\":n,\"depth\":n,\"instruction_following\":n,\"readability\":n}.")

_KEYS = ["comprehensiveness", "depth", "instruction_following", "readability"]

async def race_score(report: str, topic: str, llm: dict) -> dict:
    user = f"TOPIC:\n{topic}\n\nREPORT:\n{report[:6000]}\n\nGrade now (JSON only)."
    try:
        raw = await complete(llm["provider"], llm["model"],
                             [{"role": "system", "content": RACE_SYS}, {"role": "user", "content": user}],
                             llm.get("api_key"), max_tokens=200)
        d = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        vals = {k: max(0.0, min(10.0, float(d.get(k, 0)))) for k in _KEYS}
        vals["overall"] = round(sum(vals[k] for k in _KEYS) / len(_KEYS), 2)
        return vals
    except Exception:
        return {**{k: 0.0 for k in _KEYS}, "overall": 0.0}
