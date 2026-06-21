# Research Concierge — Google ADK multi-agent over ATHENA (via MCP)

A **Google ADK** multi-agent that takes a vague question, runs a full autonomous deep-research pass
through the **ATHENA** engine via a **Model Context Protocol (MCP) server**, and returns a short,
cited executive brief. Scaffolded with the **Agents CLI**.

This is the capstone agent layer for the **ATHENA Autonomous Deep-Research Platform**. It is a *thin*
layer: the heavy lifting (multi-round multi-provider search, source reading, two-model verification,
fact-checking, quality scoring) is done by the hardened ATHENA pipeline; this agent orchestrates it.

## Architecture

```
            ┌──── Coordinator (root LlmAgent, research_concierge) — routes by intent ────┐
            │   "new question?" → research_pipeline      "follow-up on run X?" → followup │
            └───────────────┬───────────────────────────────────────────┬─────────────────┘
                            ▼                                             ▼
┌──── research_pipeline (SequentialAgent) ────┐          ┌──── followup (LlmAgent) ────┐
│ clarifier ─► ┌── refinement_loop ──┐ ─► brief│          │ grounded Q&A over a finished │
│ (question)   │ researcher ⇄ critic │ (brief) │          │ run via get_report(run_id)   │
│              │  (LoopAgent ×2)      │         │          └──────────────┬───────────────┘
└──────────────┴──────────┬──────────┴──────────┘                        │
                          │  MCPToolset (stdio) ◄───────────────────────┘
                          ▼
        ┌──────── MCP server (athena.mcp.server) ────────┐
        │  tool: deep_research(topic, provider, ...)      │
        │  tool: get_report(run_id)                       │
        └───────────────────────┬─────────────────────────┘
                                │  HTTP (POST /api/research, poll)
                                ▼
        ┌──────── ATHENA backend — the hardened engine ───┐
        │  decompose → search → read → reflect →           │
        │  synthesize → 2-model verify → fact-check → score│
        └──────────────────────────────────────────────────┘
```
The **critic** reviews each report and either calls `exit_loop` (good enough) or refines the question to
drill a gap — so the agent *improves its own work*, bounded to 2 passes.

## The agent "skills" (sub-agents)

| Skill | Agent | Does | Reads → Writes |
|---|---|---|---|
| **Clarify** | `clarifier` | Sharpens a vague ask into one researchable question | user → `research_question` |
| **Research** | `researcher` | Calls `deep_research` (**MCP**) — drives the ATHENA engine | `research_question` → `research_report` |
| **Critique** | `critic` | Reviews the report; `exit_loop` if good, else refines for a drill pass | `research_report` → `research_question` / stop |
| **Brief** | `briefer` | Turns the report into a TL;DR + cited bullets + recommendation | `research_report` → brief |
| **Follow-up** | `followup` | Answers questions about a finished run, grounded in its sources (**MCP** `get_report`) | run_id + question → grounded answer |

## How this maps to the Kaggle course concepts

| Course concept | Where | In this repo |
|---|---|---|
| **Agent / Multi-agent system (ADK)** | code | `app/agent.py` — a coordinator over a `SequentialAgent` + a `LoopAgent` (5 agents) |
| **MCP Server** | code | `../services/api/athena/mcp/server.py` (FastMCP), consumed here via `MCPToolset` |
| **Agent skills (Agents CLI)** | code | scaffolded with `agents-cli scaffold create`; skills = the 3 sub-agents (`agents-cli-manifest.yaml`, `SKILLS.md`) |
| **Security features** | code | ATHENA backend: encrypted key vault, SSRF guard, bearer auth, prompt-injection delimiting |
| **Deployability** | — | Docker + self-healing `docker-compose.yml`, `render.yaml`, Vercel (see repo root) |

## Run it

Requires Python 3.11+, a Gemini API key (or GCP/Vertex creds), and the ATHENA backend running.

```bash
# 1. Start the ATHENA backend (the engine the MCP server talks to)
cd ..                                # repo root (athena/)
docker compose up -d --build         # backend on :7000  (add a provider key in the UI at :3000)

# 2. Install this agent + the ATHENA engine into one env
cd research-concierge
pip install -e .                     # google-adk + mcp
pip install -e ../services/api       # the `athena` package (provides `athena.mcp.server`)

# 3. Configure and run
export GOOGLE_API_KEY=...            # Gemini API key (AI Studio); or use Vertex/GCP creds
export ATHENA_API_URL=http://localhost:7000
export ATHENA_API_TOKEN=...          # only if the backend has ATHENA_API_TOKEN set
agents-cli playground                # interactive UI;  or:  adk run app
```

Ask it something like *"compare the top open-source LLM agent frameworks for production in 2026"* and
watch it clarify → research (`deep_research` via MCP) → brief.

> **Note:** `google-adk` runs cleanly on Linux / Colab / Kaggle (the course environment). On Windows
> it imports and builds (verified), but the live Gemini↔MCP run is smoothest in Colab/Kaggle.
