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
# See the License for the specific language governing permissions and
# limitations under the License.
"""Offline wiring tests — verify agent structure and the Tavily-toolset gating
without needing the network or a live MCP server. Building an MCPToolset only
stores connection params; no subprocess is launched until the tool is actually
used, so calling `_build_researcher_tools` here is safe and fast.
"""

from app import agent as agent_mod
from app.agent import (
    clarifier,
    critic,
    refinement_loop,
    research_pipeline,
    researcher,
    root_agent,
)


def _names(sub_agents) -> list[str]:
    return [a.name for a in sub_agents]


def test_top_level_structure() -> None:
    """coordinator -> [research_pipeline, followup]."""
    assert root_agent.name == "research_concierge"
    assert _names(root_agent.sub_agents) == ["research_pipeline", "followup"]


def test_pipeline_structure() -> None:
    """pipeline -> [clarifier, refinement_loop, briefer]."""
    assert research_pipeline.name == "research_pipeline"
    assert _names(research_pipeline.sub_agents) == [
        "clarifier",
        "refinement_loop",
        "briefer",
    ]


def test_refinement_loop_structure() -> None:
    """loop -> [researcher, critic]."""
    assert refinement_loop.name == "refinement_loop"
    assert _names(refinement_loop.sub_agents) == ["researcher", "critic"]


def test_critic_uses_distinct_output_key() -> None:
    """F-026: the critic must NOT share `research_question` with the clarifier.

    The clarifier owns `research_question` (the canonical question). The critic writes its
    refined drill question to a SEPARATE key so the exit-loop turn can't clobber the good
    question. The researcher must consume that distinct key on its next pass.
    """
    assert clarifier.output_key == "research_question"
    assert critic.output_key == "gap_question"
    assert critic.output_key != clarifier.output_key
    # The researcher reads the critic's gap key (optionally) so a drill pass actually drills.
    assert "{gap_question?}" in researcher.instruction
    # ...while the canonical question remains the researcher's base topic.
    assert "{research_question}" in researcher.instruction


def test_tavily_gating_disabled_without_key() -> None:
    """No TAVILY_API_KEY -> researcher gets exactly one (athena) toolset."""
    tools = agent_mod._build_researcher_tools(env={})
    assert len(tools) == 1


def test_tavily_gating_enabled_with_key() -> None:
    """TAVILY_API_KEY present -> athena + tavily toolsets (two total)."""
    tools = agent_mod._build_researcher_tools(env={"TAVILY_API_KEY": "x"})
    assert len(tools) == 2
