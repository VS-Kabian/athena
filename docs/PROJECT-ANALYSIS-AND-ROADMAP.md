# ATHENA — Project Analysis & Roadmap

**The aim:** a best-of-best, **massive, open-source AI research agent** — high accuracy, real tool-calling,
**sub-agent-driven**, that collects data from many sources, **fetches the trusted/correct info**, verifies
it hard, and synthesizes — at the standard of **Google & ChatGPT/Gemini Deep Research**.

This document is the analysis-first plan: (1) where the project stands today, (2) the 5 improvements —
their design and shipped status, (3) the forward roadmap to actually reach "best of best."

---

## Part 1 — Project condition analysis (honest, current)

ATHENA is a 3-layer agent system (**Google ADK → MCP → FastAPI engine**) with a live Next.js UI, 306
backend + 47 frontend tests, and a 4-agent audit with no critical findings. Against the aim:

| Capability toward the aim | State | Evidence |
|---|:--:|---|
| **Sub-agent-driven** research | ✅ strong | parallel metered sub-agent per facet (`graph._subagent`) + ADK Sequential/Loop agents |
| **Collect from many sources** | ✅ strong | DDG + SearXNG + **Tavily** fan-out → RRF merge → cross-encoder rerank |
| **Fetch trusted/correct info** | ✅ strong | trust-tiered validation + **multi-hop citation chasing** to primary docs/GitHub/arXiv |
| **Data verification "must blast"** | ✅ **the moat** | entailment NLI (Supported/Refuted/NEI) · cross-source conflicts · URL-liveness · 2-model verify · quality score |
| **High accuracy / grounding** | ✅ strong | section-by-section synthesis, span citations, claims audit trail, honest hallucination % |
| **Tool calling** | ✅ | MCP tools (`deep_research`/`get_report`/`rerank`/`verify`) + structured JSON outputs |
| **Methodical depth** (Gemini-like) | ✅ | coverage ledger drives drill/expand/stop; adaptive planning; never quits with a gap |
| **Cost/scale efficiency** | ✅ | model ladder (cheap tier ↔ frontier); Redis cache |
| **Multimodal / PDF-table reading** | ❌ gap | extraction is text-only — misses tables/figures (where benchmark numbers live) |
| **Code interpreter / quant analysis** | ❌ gap | can't compute or chart |
| **Reference-free factuality** | 🟡 partial | verifies vs *cited* source; doesn't re-check vs *fresh* search |
| **Durable/async + editable plan** | 🟡 partial | in-memory run (heartbeat-kept); no suspend/resume for a pre-run editable plan |
| **Raw scale** (100s of pages) | 🟡 by design | bounded for cost/rate-limits; quality-over-brute-force |

**Read:** ATHENA already does the *hard, differentiating* part — **verifiable trust + methodical,
sub-agent-driven depth** — at a level most open-source agents don't reach. The remaining gaps to "Google/
ChatGPT-research standard" are **modality** (PDF/tables, code/charts), **reference-free re-verification**,
and **durable orchestration with an editable plan** — not the core research loop.

---

## Part 2 — The 5 improvements: plan & status (designed, then shipped)

These were scoped via the brainstorming → writing-plans flow (plan: `docs/plans/2026-06-21-deep-research-upgrades-plan.md`)
and **all 5 are implemented, tested, and live.**

| # | Improvement | Design decision (the "logic") | Status | Where |
|---|---|---|:--:|---|
| 1 | **Multi-hop citation chasing** | After reading, harvest a page's outbound links → rank by domain authority → fetch a **bounded, SSRF-guarded 2nd hop** → primaries join the pool/coverage. No 3rd hop, no LLM cost. | ✅ shipped | `agents/hop.py`, `fetch.fetch_html` |
| 2 | **Section-by-section synthesis** | Outline → per-section targeted re-rank of the pool → grounded write per section, **globally-consistent `[n]` citations**; single-pass fallback. | ✅ shipped | `agents/synthesizer.py:synthesize_sections` |
| 3 | **Adaptive planning** | Facets stay *stable* for coverage attribution but the planner **appends** new facets (capped) when scope is covered — "plan → iterate" without breaking the ledger. | ✅ shipped | `agents/planner.expand_facets`, `graph.py` |
| 4 | **GraphRAG memory** | Extract (subject, predicate, object) triples from **validated** sources → Postgres `kg_*` tables → 1-hop neighborhood into synthesis context. Opt-in flag. | ✅ shipped | `agents/graphmem.py`, `migrations/008` |
| 5 | **Model ladder** | `for_role()` routes cheap/fast tier to plan/triage/link-rank/outline/entailment; frontier to synthesis. BYO key. | ✅ shipped | `gateway/ladder.py` |

Plus the trust-layer rebuild that motivated them: **entailment replaced cosine**, **conflict detection**,
**URL-liveness**, NEI calibration, claim-relevant excerpts — the "verification must blast" requirement.

---

## Part 3 — Forward roadmap to "best of best" (next levers)

To close the remaining gaps vs Google/ChatGPT Deep Research, in impact order:

**NOW (highest impact, no new infra):**
1. **Reference-free factuality** — re-verify the top claims against a *fresh, neutralized* search (not just
   the cited source). Defeats the "cited-but-wrong" failure mode. *Effort: M.*
2. **PDF-table / layout-aware extraction** (marker-pdf / LlamaParse) — read the tables where benchmark
   numbers actually live; today they're flattened. *Effort: M.*

**NEXT (depth + UX that judges/users feel):**
3. **Editable research plan + suspend/resume** — show the plan, let the user edit before compute burns
   (Gemini "Collaborative Planning"); needs a durable runner (arq on the existing Redis). *Effort: M–L.*
4. **Sandboxed code interpreter** — compute/verify quantitative claims + generate inline charts. *Effort: L (gate behind auth).*
5. **Eval at scale** — expand the independent-judge regression set; add citation-accuracy + reference-free
   metrics; track quality run-over-run. *Effort: M.*

**LATER (scale & breadth):**
6. More providers (news/academic APIs) + hybrid API+browser retrieval; orchestrator-worker parallelism under
   a metered token budget; multi-tenant auth + RLS.

**The moat to protect:** don't chase Google's compute/scale — **win on verifiable, auditable trust.** Every
lever above either deepens trust (1, 5), unlocks richer sources (2, 6), or makes the depth visible (3, 4).

---

*Status: the 5-improvement plan is complete and shipped; this roadmap is the forward path toward the
full "best of best" aim. The project + Kaggle submission docs are rubric-ready (see `KAGGLE-CHECKLIST.md`).*
