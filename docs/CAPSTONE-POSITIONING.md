# ATHENA — Capstone Positioning (the spine for the writeup + video)

## One-liner
**ATHENA is an autonomous multi-agent research analyst that delivers a *verified, cited* brief — not a confident hallucination.** Every claim is cross-checked by a second model and scored for hallucination risk, so you get research you can actually act on.

## Track
**Agents for Business** — "driving insights" / decision research is an explicit fit. *(Freestyle is the fallback if we want to lead with engineering depth.)*

## The problem (vivid + specific)
A founder, product manager, or analyst has to make a decision and needs to understand a market, a competitor set, or a technical landscape **today**. Their options:
- **Hours of manual googling** through SEO listicles that all say the same shallow thing, or
- **An AI chatbot** that answers in seconds — *confidently, fluently, and often wrong*, with weak or fabricated citations.

Neither is trustworthy enough to put in front of a boss, an investor, or a customer. The bottleneck isn't *generating* text — it's **trusting** it.

## Why agents (uniquely)
A single LLM call can't do this. Trustworthy research needs a **loop of specialized agents**: decompose the question, search many sources, *read* them, reflect on gaps, drill deeper, synthesize, and then — critically — **a second, independent model re-checks every claim against its source**, and a fact-checker scores hallucination risk. That division of labor + adversarial verification is exactly what an agent system is for, and it's why ATHENA's output is trustworthy where a chatbot's isn't.

## The solution
A **Google ADK multi-agent** ("Research Concierge") — *clarify → research → brief* — that drives the hardened **ATHENA engine** through an **MCP server**. The engine runs the full research loop; the ADK agents turn a vague ask into a sharp question and the long report into a crisp, cited executive brief.

## The signature "wow" (make this land on camera)
1. **Adversarial verification** — a *second model* independently re-checks every cited claim against its source and corrects/flags contradictions.
2. **Hallucination-risk score + span-level citations** — each report ships with a 0–100 quality score, a hallucination-risk %, and the single most-relevant sentence per source.
3. **It shows its work** — the live knowledge graph + round-by-round reasoning ("only 3 validated sources — drilling for primary docs") make the agent's thinking visible.

## The three demo moments that MUST land in the video
1. **Ask → watch it think** — type a real question; the agent clarifies it, then the graph fills with sources round by round as it drills for *primary* sources.
2. **The verification beat** — point at "second-model verification: N claims corrected/flagged" + the hallucination-risk score. This is the differentiator; pause on it.
3. **The brief** — the ADK Briefer turns the full report into a 5-bullet cited brief. "From a vague question to a decision-ready, verified brief — in minutes."

## What we are NOT claiming
Not "the smartest model." The claim is **trust**: verified, cited, scored. That's the wedge.
