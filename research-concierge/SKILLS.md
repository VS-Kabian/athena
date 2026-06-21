# Agent Skills — research_concierge

This ADK agent is composed of five **skills** (sub-agents). A top-level coordinator (`research_concierge`,
an `LlmAgent`) routes the user: a NEW question → the `research_pipeline` (`SequentialAgent`:
*Clarify → (Research ↔ Critique loop) → Brief*, where Research and Critique sit inside a `LoopAgent`
that refines until the report is good, max 2 passes); a FOLLOW-UP about a finished run → `followup`.
State is passed between skills via the session (`output_key` writes; `{key}` reads in instructions).

| # | Skill | Agent name | Input (state) | Output (state) | Tools |
|---|-------|------------|---------------|----------------|-------|
| 1 | **Clarify** | `clarifier` | user request | `research_question` | — |
| 2 | **Research** | `researcher` | `research_question` | `research_report` | `deep_research` (MCP) |
| 3 | **Critique** | `critic` | `research_report` | refined `research_question` *or* `exit_loop` | `exit_loop` |
| 4 | **Brief** | `briefer` | `research_report` | final brief (response) | — |
| 5 | **Follow-up** | `followup` | run_id + question | grounded answer | `get_report` (MCP) |

## Skill details

### 1. Clarify (`clarifier`)
Turns a vague request into ONE precise, researchable question, resolving scope (timeframe, region,
comparison set) with stated defaults. Keeps the pipeline focused so research isn't wasted on an
ambiguous prompt.

### 2. Research (`researcher`)
The core skill. Calls the **`deep_research` MCP tool** (served by `athena.mcp.server`), which drives
the full ATHENA engine: multi-provider search, mid-loop reading, reflective deep-research controller,
synthesis, two-model verification, fact-check, and a 0–100 quality score. Returns the cited report.

### 3. Critique (`critic`) — self-improvement
Reviews the report. If it's thorough and well-cited, it calls the **`exit_loop`** tool to finish.
Otherwise it outputs a refined sub-question targeting the biggest gap, and the **`LoopAgent`** sends the
researcher back in to drill (bounded to 2 passes). This is the agent holding its own work to a standard
— the "research that improves itself" beat.

### 4. Brief (`briefer`)
Condenses the long report into an executive brief: a 3-sentence TL;DR, 5–7 cited key findings, and a
one-line recommendation — preserving the `[n]` citation markers from the report.

## New engine skills attachable via MCP

The ATHENA MCP server now also exposes two extra skills that the **`researcher`** picks up automatically
through the same `_athena_toolset()` MCPToolset (no separate wiring needed):

- **`rerank_sources(query, passages)`** — cross-encoder rerank that reorders candidate passages by true
  relevance to the query, so the strongest evidence surfaces first.
- **`verify_claims(report_markdown, sources, provider, model)`** — second-model verification that
  re-checks the report's claims against its sources, providing an independent self-check pass.

### Optional external-MCP search (Tavily)

The agent can ALSO connect to a standard third-party search MCP server — the official **Tavily MCP
server** (`npx -y tavily-mcp`) — for fresh web results. It is gated on the `TAVILY_API_KEY` env var
(`_build_researcher_tools` appends `_tavily_toolset()` only when the key is set), so it never breaks
when absent. This demonstrates ADK connected to a standard external MCP server, in addition to
ATHENA's own MCP server.

## Scaffolding
Created with the **Agents CLI**:
```bash
agents-cli scaffold create research_concierge --prototype --deployment-target none
```
The CLI manifest is `agents-cli-manifest.yaml`. Run locally with `agents-cli playground` or `adk run app`.
