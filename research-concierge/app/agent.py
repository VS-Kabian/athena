# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.

"""Research Concierge — a Google ADK multi-agent that runs ATHENA deep research via an MCP server.

Pipeline (SequentialAgent):  clarifier -> researcher (MCP) -> briefer

  - clarifier : sharpens a vague ask into one researchable question      (-> state['research_question'])
  - researcher: calls the `deep_research` MCP tool, which drives the ATHENA engine
                (multi-round search/read/verify/score)                   (-> state['research_report'])
  - briefer   : turns the long report into a short, cited executive brief

The researcher's tool comes from an MCPToolset that launches ATHENA's MCP server
(`python -m athena.mcp.server`) over stdio — so this demonstrates ADK multi-agent + MCP together.

Session-state flow (who writes / reads which key):

  - clarifier  WRITES research_question   (the canonical question; set once, never overwritten)
  - researcher READS  research_question + gap_question? ; WRITES research_report
  - critic     READS  research_report ; either calls exit_loop OR WRITES gap_question
                (a DISTINCT key — it never clobbers research_question, see F-026)
  - briefer    READS  research_report
  - followup   uses the `get_report` MCP tool (no shared pipeline state)

On the first refinement-loop pass `gap_question` is unset, so the researcher works the original
`research_question`. If the critic finds a gap it writes `gap_question`; the next researcher pass
then drills into that gap while `research_question` stays intact for any later reader.
"""
import os
import sys

from google.adk.agents import LlmAgent, LoopAgent, SequentialAgent
from google.adk.apps import App
from google.adk.tools.mcp_tool import MCPToolset, StdioConnectionParams
from google.adk.tools.tool_context import ToolContext
from mcp import StdioServerParameters

# Auth: prefer a Gemini API key (AI Studio — works in Colab/Kaggle) if provided; otherwise fall back
# to Vertex AI via the ambient GCP credentials the Agents CLI configured.
if os.environ.get("GOOGLE_API_KEY"):
    os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "False")
else:
    try:
        import google.auth

        _, project_id = google.auth.default()
        os.environ.setdefault("GOOGLE_CLOUD_PROJECT", project_id or "")
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "True")
    except Exception:
        pass

MODEL = os.environ.get("ADK_MODEL", "gemini-flash-latest")

# A fresh MCPToolset launches ATHENA's MCP server over stdio. The `athena` package must be importable
# in this env (`pip install -e services/api`); ATHENA_API_URL / ATHENA_API_TOKEN are forwarded.
# This server also exposes the `rerank_sources` and `verify_claims` skills, so the researcher gets
# them automatically through this same toolset.
def _athena_toolset() -> MCPToolset:
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", "athena.mcp.server"],
                env={k: v for k, v in os.environ.items()
                     if k in ("ATHENA_API_URL", "ATHENA_API_TOKEN", "PATH", "SystemRoot", "SYSTEMROOT")},
            ),
        ),
    )


# Optional: connect to a STANDARD third-party search MCP server — the official Tavily MCP server.
# This demonstrates ADK connected to a standard external MCP server, in addition to ATHENA's own
# MCP server. Gated on TAVILY_API_KEY so it NEVER breaks when absent. The package version is PINNED
# (override via TAVILY_MCP_SPEC) so a runtime `npx` install can't silently pull a hijacked release.
TAVILY_MCP_SPEC = os.environ.get("TAVILY_MCP_SPEC", "tavily-mcp@0.2.9")


def _tavily_toolset() -> MCPToolset:
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command="npx",
                args=["-y", TAVILY_MCP_SPEC],
                env={k: v for k, v in os.environ.items()
                     if k in ("TAVILY_API_KEY", "PATH", "SystemRoot", "SYSTEMROOT")},
            ),
        ),
    )


# Pure helper so the gating logic is testable without import-time env coupling: always include
# ATHENA's toolset; add the Tavily external-MCP toolset ONLY when a TAVILY_API_KEY is present.
def _build_researcher_tools(env: dict | None = None) -> list:
    env = os.environ if env is None else env
    tools = [_athena_toolset()]
    if env.get("TAVILY_API_KEY"):
        tools.append(_tavily_toolset())
    return tools


# F-028 — IMPORT-TIME CONTRACT (read before moving the key-set in a notebook):
# The researcher's toolset is resolved ONCE here, at module import, from the *current* process env.
# Tavily is attached only if TAVILY_API_KEY is already set at this point. In Colab/Kaggle, where
# cells mutate os.environ incrementally, you MUST export TAVILY_API_KEY *before* importing this
# module (e.g. set it, then `import app.agent`) — setting it in a later cell will NOT retro-attach
# Tavily. If you need late/lazy attachment, call `_build_researcher_tools(env)` again and rebuild
# the `researcher` agent's `tools`; the pure helper above is deliberately env-injectable for that.
_researcher_tools = _build_researcher_tools()

# ── Skill 1: Clarifier ────────────────────────────────────────────────────
clarifier = LlmAgent(
    name="clarifier",
    model=MODEL,
    instruction=(
        "You sharpen the user's request into ONE precise, researchable question. Resolve vague scope "
        "(timeframe, region, comparison set) with sensible defaults and state them inline. "
        "Output ONLY the refined question — no preamble."
    ),
    output_key="research_question",
)

# ── Skill 2: Researcher (uses the ATHENA deep_research MCP tool) ───────────
researcher = LlmAgent(
    name="researcher",
    model=MODEL,
    instruction=(
        "You are a research operator. Your PRIMARY tool is `deep_research`. "
        "The base question is: {research_question}. "
        "A critic may also have flagged a specific gap to drill into: {gap_question?}. "
        "If that gap is non-empty, focus this pass on it (still grounded in the base question); "
        "otherwise research the base question itself. Call `deep_research` with the resulting "
        "topic (use rounds=3 and deep=true for broad/comparative topics). "
        "You MAY also use the `tavily` search tools for fresh web results when they help, and the "
        "`rerank_sources` / `verify_claims` skills to sharpen and self-check your findings. When done, "
        "output the `deep_research` tool's `report_markdown` verbatim, prefixed with one line: "
        "'Quality: <quality_score>/100, <N> sources.' If the tool returns an error, say so plainly."
    ),
    tools=_researcher_tools,
    output_key="research_report",
)

# ── Skill 3: Critic (self-critique) — stops the loop or refines the question for a drill pass ──
def exit_loop(tool_context: ToolContext) -> dict:
    """Call this ONLY when the research report is thorough and well-cited — it ends the refinement loop."""
    tool_context.actions.escalate = True   # signal the LoopAgent to stop iterating
    return {"status": "sufficient"}


critic = LlmAgent(
    name="critic",
    model=MODEL,
    instruction=(
        "You are a rigorous research critic. Review the report in {research_report}. "
        "If it thoroughly answers the question with cited, verified claims and few gaps, call the "
        "`exit_loop` tool to finish. OTHERWISE, do NOT call exit_loop — instead output ONLY a single "
        "refined sub-question targeting the most important gap or weakest-evidence area, so the "
        "researcher can drill into it next."
    ),
    tools=[exit_loop],
    # F-026 — write the refined drill question to a DISTINCT key (`gap_question`), NOT
    # `research_question`. The researcher reads it as {gap_question?}. This keeps the canonical
    # `research_question` (written once by the clarifier) intact even on the exit-loop turn, where
    # ADK would otherwise persist this agent's (possibly empty) output over the good question.
    output_key="gap_question",
)

# refine-until-good loop: research -> critique -> (drill again | stop), bounded so it can't run away
refinement_loop = LoopAgent(
    name="refinement_loop",
    sub_agents=[researcher, critic],
    max_iterations=2,
)

# ── Skill 4: Briefer ──────────────────────────────────────────────────────
briefer = LlmAgent(
    name="briefer",
    model=MODEL,
    instruction=(
        "Turn the research report in {research_report} into a crisp executive brief: a 3-sentence "
        "TL;DR, then 5-7 key findings as bullets (each keeping its [n] citation marker), then a "
        "one-line bottom-line recommendation. Do not invent facts beyond the report."
    ),
)

# ── The research pipeline: clarify -> (research <-> critique loop) -> brief ──
research_pipeline = SequentialAgent(
    name="research_pipeline",
    description="Clarifies a question, runs ATHENA deep research with a self-critique loop, then briefs the result.",
    sub_agents=[clarifier, refinement_loop, briefer],
)

# ── Skill 5: Follow-up Q&A — answers questions about a finished run, grounded in its sources (MCP get_report) ──
followup_agent = LlmAgent(
    name="followup",
    model=MODEL,
    description="Answers follow-up questions about a completed ATHENA research run, grounded only in its sources.",
    instruction=(
        "The user is asking a follow-up about a finished research run. If you don't have the run_id, ask "
        "for it. Then call `get_report(run_id)` and answer ONLY from that report and its sources, keeping "
        "[n] citation markers. If the answer isn't supported by the report, say so plainly and offer to "
        "run fresh research instead — never guess."
    ),
    tools=[_athena_toolset()],
)

# ── Coordinator (root): routes a NEW question to the pipeline, a FOLLOW-UP to the grounded Q&A agent ──
root_agent = LlmAgent(
    name="research_concierge",
    model=MODEL,
    description="Research concierge that routes new research vs. follow-up questions to the right agent.",
    instruction=(
        "You are a research concierge. Decide and delegate:\n"
        "- If the user wants to research a NEW topic or question, transfer to `research_pipeline`.\n"
        "- If the user is asking a FOLLOW-UP about an already-finished run (they give a run_id or refer "
        "to a previous report), transfer to `followup`.\n"
        "Briefly say which you're doing, then transfer. Don't answer research questions yourself."
    ),
    sub_agents=[research_pipeline, followup_agent],
)

app = App(root_agent=root_agent, name="research_concierge")
