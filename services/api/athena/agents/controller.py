"""Reflective controller for the optional autonomous "deep" research mode.

The default pipeline runs a fixed number of rounds. In deep mode, after each round the
controller reflects on what's been found and decides whether to STOP early (coverage is
strong), DRILL into a specific gap with narrower questions, or CONTINUE with fresh angles.
This adds agency without replacing the deterministic retrieval/synthesis the rest of the
graph depends on — and it degrades gracefully to "continue" whenever the model is unavailable.
"""
import json

from ..gateway.llm import complete

REFLECT_SYS = (
    "You are the controller of an autonomous research agent. Given the topic, the sub-questions "
    "already explored, and the titles/snippets found so far, decide the next action. Respond ONLY "
    'with a JSON object: {"action": "stop"|"continue"|"drill", "questions": [up to 3 new '
    'sub-questions], "reason": "one short sentence"}. '
    "'stop' = the major facets are already well covered and more searching adds little. "
    "'drill' = a specific gap or promising thread deserves deeper, narrower questions (put them in 'questions'). "
    "'continue' = broaden with fresh angles (put them in 'questions'). "
    "Prefer 'stop' once coverage is good AND there are enough validated, on-topic sources; "
    "do NOT 'stop' while validated sources are below the target — keep researching for authoritative primary "
    "sources (official docs, GitHub, standards, reputable press) instead of padding with low-quality blogs."
)


async def reflect(topic: str, findings: str, explored: list[str], round_no: int,
                  max_rounds: int, llm: dict, validated: int = 0, target: int = 0) -> dict:
    """Decide the next research action. Always returns a dict with keys action/questions/reason."""
    if round_no >= max_rounds:
        return {"action": "stop", "questions": [], "reason": "reached round budget"}
    suff = (f"Validated on-topic sources so far: {validated} (target ~{target}). "
            f"{'Sufficient — stopping is reasonable if coverage is good. ' if target and validated >= target else 'Below target — prefer continue/drill to find authoritative primary sources. '}"
            if target else "")
    prompt = (f"Topic: {topic}\nRound: {round_no}/{max_rounds}\n"
              f"Sub-questions explored: {explored}\n"
              f"{suff}\n"
              f"Findings so far (titles/snippets):\n{(findings or '')[:2500]}\n\n"
              "Decide the next action as JSON.")
    try:
        raw = await complete(
            llm["provider"], llm["model"],
            [{"role": "system", "content": REFLECT_SYS}, {"role": "user", "content": prompt}],
            llm.get("api_key"), max_tokens=2000, timeout=120)
        obj = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        action = str(obj.get("action", "continue")).lower()
        if action not in ("stop", "continue", "drill"):
            action = "continue"
        questions = [str(q).strip() for q in (obj.get("questions") or []) if str(q).strip()][:3]
        reason = str(obj.get("reason", ""))[:200]
        return {"action": action, "questions": questions, "reason": reason}
    except Exception:
        # reflection unavailable -> behave like the default pipeline (caller falls back to refine)
        return {"action": "continue", "questions": [], "reason": "reflection unavailable"}
