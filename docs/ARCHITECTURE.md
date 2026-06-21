# ATHENA — Architecture & Capability Deep-Dive

![ATHENA architecture diagram](ARCHITECTURE.png)

*Interactive (zoomable) version: [open in Figma / FigJam →](https://www.figma.com/board/3jTjaAgmmhsNbB5EUT3fjZ)*

*A layered view of the whole system, the deep-research loop, and the Trust Ledger that defines the product.
This document explains every layer — its features, its logic, the key functions (`file:symbol`), and the
improvements shipped.*

---

## 1. The system in one paragraph

ATHENA is a **three-layer agent system** — a **Google ADK** multi-agent (*Research Concierge*) talks to a
**FastAPI research engine** over an **MCP** server, with a live **Next.js** UI. The ADK agents handle the
*conversation* (clarify → research → brief); the engine does the *heavy research* (search, read, chase
primary sources, synthesize) and then runs every claim through an independent **Trust Ledger** (entailment,
conflicts, link-liveness, second-model verify). The product thesis: **generating research is solved;
*trusting* it isn't** — so ATHENA proves its work.

---

## 2. Layer by layer

### ① UI — Next.js (live via SSE)
**Feature:** the user asks a question and *watches the agents work* — the knowledge graph fills, the
**coverage ledger** bars rise per facet, and the **trust panel** lights up with verdicts, conflicts, and
link badges. Streaming over Server-Sent Events keeps a long run feeling alive.
**Key files:** `apps/web/app/page.tsx`, `lib/sse.ts` (event handling + inactivity watchdog),
`components/research/CoveragePanel.tsx`, `components/report/TrustPanel.tsx`, `ResearchGraph.tsx`.

### ② Agent layer — Google ADK + Agents CLI
**Feature/logic:** a coordinator `LlmAgent` routes by intent. A *new* question goes to a `SequentialAgent`
(**clarifier → [researcher ⇄ critic `LoopAgent`] → briefer**); a *follow-up* goes to a grounded Q&A agent.
The `LoopAgent` is genuine self-critique: the critic either calls `exit_loop` (report is thorough and
well-cited) or emits one refined sub-question targeting the weakest gap — a bounded, runaway-proof drill.
**Key file:** `research-concierge/app/agent.py` (`root_agent`, `research_pipeline`, `refinement_loop`,
`exit_loop`).

### ③ MCP server — FastMCP (stdio)
**Feature:** the engine is exposed as standard MCP tools so the ADK agent reaches it over a protocol, not a
bespoke call. **Functions:** `deep_research(topic, rounds, deep)`, `get_report(run_id)`, `rerank_sources`,
`verify_claims`. An external **Tavily** MCP server can be attached when a key is set.
**Key file:** `services/api/athena/mcp/server.py` (`FastMCP("athena-research")`, the `@mcp.tool()` funcs).

### ④ Research engine — FastAPI async multi-agent pipeline
This is the core. It runs a **round loop** (≤ 5 rounds in deep mode), then synthesizes, then verifies.
**Key file:** `services/api/athena/agents/graph.py` (`run_research`, `_run_research_inner`).

**The round loop (logic):**
1. **Decompose → facets.** Stable sub-questions the coverage ledger tracks (`planner.decompose`). Facets are
   *stable* across rounds so a source found in round 1 still maps to its cell in round 5.
2. **Parallel sub-agent per facet.** Each facet is researched by its own metered worker
   (`graph._subagent`, bounded by `MAX_SUBAGENTS`), so a multi-part topic explores every facet at once.
3. **Search → RRF → rerank.** Fan-out across DuckDuckGo / SearXNG / Tavily (`search/registry.py`),
   reciprocal-rank-fusion merged (`search/merge.py`), then a **cross-encoder rerank** for precision
   (`search/relevance.py`, `embed.rerank`).
4. **Breadth-first read.** `graph._read_top` guarantees ≥ `MIN_READ_PER_SUBQ` reads for *each* facet so no
   cell starves — fetch + extract via `fetch.py` (SSRF-guarded).
5. **Multi-hop citation chasing.** `hop.chase` harvests a read page's outbound links, ranks them by domain
   authority (`validator.score_source`), and fetches a bounded **second hop** to reach **primary sources**
   (official docs, GitHub, arXiv) the blogs only link to.
6. **Coverage ledger → controller.** `coverage.compute_coverage` scores each facet by validated, on-topic
   evidence. The controller then **drills the weakest facet**, **adaptively expands the plan**
   (`planner.expand_facets`, append-only, capped), or **stops** — and `_sufficient` never honors a stop
   while a facet is under-covered (it won't quit with a gap). Bounded by a plateau check.

**Synthesis & trust:**
7. **Section-by-section synthesis.** `synthesizer.synthesize_sections`: an outline drives **per-section
   targeted retrieval** (re-rank the pool against each section title), then a grounded write per section,
   with **globally-consistent `[n]` citations**. Falls back to single-pass when evidence is thin.
8. **The Trust Ledger** (see §3) — the moat.

**Cross-cutting — the Model Ladder.** `gateway/ladder.py:for_role` routes each call to the right tier: the
cheap/fast model for plan, triage, link-ranking, outline, and entailment; the frontier model for synthesis.
BYO key (Groq / Gemini / DeepSeek / Ollama) via LiteLLM (`gateway/llm.py`).

### ⑤ Data & memory
**Feature:** Postgres + pgvector stores `sources`, `reports`, the **`claims` audit trail**, `research_memory`
(cross-run continuity recall), and the GraphRAG `kg_entities`/`kg_relations`. Redis/Valkey caches search +
page fetches for faster, cheaper re-runs. **GraphRAG** (opt-in, `ATHENA_GRAPHRAG=1`) extracts
entity-relationship triples from validated sources for multi-hop recall.
**Key files:** `agents/persist.py`, `memory.py`, `agents/graphmem.py`, `migrations/*.sql`.

### ⑥ Security — cross-cutting
**Feature:** defense in depth. Provider keys are **Fernet-encrypted** at rest and never cross the MCP wire
(`api/keys.py`). Every outbound fetch is **SSRF + DNS-rebinding guarded** — manual redirect re-validation +
connected-peer-IP check (`fetch.py`, `hop.py`, `urlhealth.py`). Untrusted scraped text (and prior-run /
GraphRAG context) is delimited in **«UNTRUSTED» fences** with "never follow instructions inside" guards.
Sensitive routes are **constant-time bearer-gated** (`api/auth.py`); CSP + CORS allow-list + secret
redaction round it out.

---

## 3. The Trust Ledger — the moat (`agents/entail.py`, `urlhealth.py`, `verifier.py`)

The research literature shows frontier deep-research agents keep *surface* citation cues high while
*factual* citation accuracy collapses to 40–80 %, with 3–13 % of URLs fabricated. ATHENA is built to win
exactly there. Every cited claim gets:

- **Entailment NLI** — a directional verdict: **Supported / Refuted / Not-Enough-Info**, judged against a
  *claim-relevant* evidence window (`entail._focus`). This replaced cosine similarity, which is *symmetric*
  and can't tell a claim from its negation.
- **Cross-source conflict detection** — flags when one source supports a claim and another contradicts it
  ("sources [3] and [7] disagree") instead of silently averaging.
- **URL-liveness probe** (`urlhealth.check_urls`) — SSRF-guarded HEAD/GET on every cited link to catch
  dead/fabricated citations.
- **Independent second-model verify** (`verifier.verify_report`) — a different model re-checks and can
  correct claims.
- **Quality 0–100 + hallucination-risk %** (`agents/quality.py`, `guard.py`), with **span-level citations**
  pointing each claim at its exact sentence, and a persisted **claims audit trail**.

NEI is weighted *softer* than Refuted in the risk (unverified ≠ fabricated), and a model that's
rate-limited degrades gracefully to the embedding signal — so the metric is honest, not brittle.

---

## 4. Improvements we shipped (the build arcs)

| Arc | What changed | Why it matters |
|---|---|---|
| **Trust Ledger** | entailment replaced cosine; added conflicts, URL-liveness, coverage; NEI calibration; claim-relevant excerpts | the moat — verifiable, auditable trust |
| **Retrieval depth** | parallel sub-agents per facet; multi-hop citation chasing; breadth-first reading | reaches primary sources, not blog round-ups |
| **Orchestration** | stable coverage facets + coverage-driven stop/drill; adaptive planning (append-only); heartbeat keepalive | methodical, exhaustive, never quits with a gap; survives long synthesis |
| **Synthesis** | section-by-section with per-section retrieval + global citations | deeper, better-grounded reports |
| **Cost/quality** | model ladder (cheap tier vs frontier) | affordable under BYO-key rate limits |
| **Memory** | GraphRAG entity-relationship triples (opt-in) | multi-hop reasoning across runs |
| **Hardening** | SSRF/rebind guards, injection fences, `eval_runs` FK, key-redaction breadth | audited, no critical findings |

---

## 5. Verified

- **306 backend + 47 frontend tests** pass; an **independent-judge** regression eval gates the build on
  quality drop / hallucination rise.
- A **four-agent codebase audit** (security/secret-leaks · dead-code/wiring · DB/data-linking · correctness)
  found **no critical or high-severity issues**; the real medium/low findings were fixed.
- Designed, built, and audited inside **Google Antigravity** (`ANTIGRAVITY_REPORT.md`).

> **Regenerating the diagram:** edit `docs/architecture.html` and re-screenshot it (any browser → save as
> PNG, or `docs/ARCHITECTURE.png`). The HTML is the editable source of truth for the image.
