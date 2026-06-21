# ATHENA — Demo Video Script (≤ 5 min)

**Why this matters:** judges almost never run your full stack (Postgres + Redis + SearXNG + API keys).
**This video is how they see it work.** Hit all five beats (Problem · Why agents · Architecture · Demo ·
The Build) in ≤ 5:00 — and protect the **Demo** and the **Trust-Ledger beat**: that's what wins.

**Record:** 1080p screen capture + clear voiceover. Pre-run ATHENA once on a topic where it shines (a
comparative/technical question with real primary sources, e.g. *"Compare LangGraph, CrewAI, AutoGen, and
Google ADK for production AI agents in 2026"*) so a strong result is cached/ready. Have **deep mode** on,
a verifier model set, and **Fast model = a non-reasoning model** (e.g. `deepseek-v4-flash`) so the trust
layer renders cleanly. Upload to YouTube as **Public** or **Unlisted** (never Private).

---

### Scene 1 — Hook + Problem · 0:00–0:30
- **SHOW:** a title card → an AI chatbot answering a research question fast, with a made-up/uncited stat highlighted in red.
- **SAY:** *"You have to make a decision and research a market today. So you ask an AI — it answers in seconds, confidently… and often wrong, with citations it made up. Studies show frontier research agents fabricate 3 to 13 percent of their citation URLs, and almost nobody checks. The hard part of research was never writing the text. It's trusting it. That's the problem ATHENA solves."*

### Scene 2 — What ATHENA is + Why agents · 0:30–1:00
- **SHOW:** the ATHENA UI home screen.
- **SAY:** *"ATHENA is an autonomous, multi-agent research analyst. One model can't be trusted to research itself — so ATHENA uses a team of agents: parallel sub-agents decompose the question and search the open web, read the sources, **chase citations to primary documents**, and then an independent trust layer re-checks every claim against its source. You get a verified, cited brief — not a confident guess."*

### Scene 3 — Architecture · 1:00–1:30
- **SHOW:** the architecture diagram (from the README): ADK SequentialAgent → MCP → engine.
- **SAY:** *"It's built on the course stack. A **Google ADK** multi-agent — clarify, research, brief — calls the ATHENA research engine through an **MCP server**. The ADK agents are the skills; the MCP tool is how they reach the engine that does the heavy lifting."*

### Scene 4 — DEMO (the heart) · 1:30–3:45
- **4a · Ask (1:30–1:50)** — **SHOW:** type a real comparative question; turn on **deep mode**; hit Start. **SAY:** *"I ask one question…"*
- **4b · Watch it think (1:50–2:35)** — **SHOW:** the live knowledge graph filling; the **Coverage Ledger** bars filling per facet; sources tagged **`hop`** appearing (the primaries it chased); the reasoning panel. **SAY:** *"…and watch it work. Each sub-question is its own agent, running in parallel. The **coverage ledger** shows it isn't done until every facet is covered — and it doesn't stop at blog posts: it **follows their citations to the primary sources** — official docs, GitHub, benchmarks. That's the agent reasoning, live."*
- **4c · THE TRUST LEDGER (2:35–3:15) — pause here, this is the win.** **SHOW:** zoom on the **Verification & Trust** panel: *Entailment NLI · N claims checked*, the **Supported / Refuted / Not-Enough-Info** tally, a **cross-source conflict** flag, the **links-live** ratio, the hallucination-risk %, and a span-level citation tooltip. **SAY:** *"Here's the difference. Every claim gets a directional **entailment verdict** — supported, refuted, or not-enough-info — not a fuzzy similarity score. It flags where **sources disagree**. It **probes every link** to catch fabricated citations. And every claim points to the exact sentence it came from. This is research you can defend."*
- **4d · The brief (3:15–3:45)** — **SHOW:** the ADK Research Concierge turning the report into a 5-bullet cited executive brief. **SAY:** *"And the ADK agent turns that whole verified report into a decision-ready brief — TL;DR, cited findings, a recommendation. Vague question to verified brief, in minutes."*

### Scene 5 — The Build · 3:45–4:30
- **SHOW:** quick cuts: `agent.py` (SequentialAgent + LoopAgent), `mcp/server.py`, the docker-compose, a test run going green (**306 passing**), the Antigravity report.
- **SAY:** *"Under the hood: a Google ADK multi-agent over an MCP server, on a hardened FastAPI engine — parallel sub-agents, multi-hop citation chasing, section-by-section synthesis, entailment-based verification, pgvector memory. Security throughout: an encrypted key vault, SSRF protection, prompt-injection guards. Self-healing Docker deploy. Three hundred-plus tests, and a four-agent audit with no critical findings. I designed, built, and audited the whole thing inside **Google Antigravity**."*

### Scene 6 — Close · 4:30–5:00
- **SHOW:** the finished cited brief + the trust panel on screen; end title with the repo/demo URL.
- **SAY:** *"Most AI tells you what it thinks. ATHENA shows you what it can prove — every claim verified, conflicts surfaced, links checked, hallucination risk scored. An autonomous research analyst you can actually trust. Thanks for watching."*

---

## Timing cheat-sheet
| Beat | Time | Don't exceed |
|---|---|---|
| Problem | 0:30 | keep it tight |
| What / Why agents | 0:30 | |
| Architecture | 0:30 | |
| **Demo** | **2:15** | most important — protect this time |
| The Build | 0:45 | quick cuts |
| Close | 0:30 | |

**If you're over 5:00:** cut Scene 3 to 15 s and trim 4b — **never cut 4c (the Trust Ledger)**; that's the win.
