# ATHENA Research-Quality Execution Plan (Hallucination < 10%) — v1

**Author:** Principal AI Research-Systems Engineer
**Method:** Built on the June-2026 file-by-file audit (`docs/RESEARCH-QUALITY-AUDIT-2026-06.md`, 5 subsystem
passes over ~40 backend + ~27 frontend files), cross-checked against the current literature on RAG
faithfulness (RAGAS, ALCE), corrective/self-grounding generation (CRAG, Self-RAG, Chain-of-Verification),
and the 2026 retrieval stack (BGE-M3 + BGE-reranker-v2). This document is the **execution plan** — *how* we
implement each item in this codebase, in what order, with which signatures, tests, and acceptance gates.
Every step cites a real `file:symbol`.

> **Companion docs.** The *what/why* lives in `RESEARCH-QUALITY-AUDIT-2026-06.md`; the *correctness/security*
> baseline lives in `ANTIGRAVITY_REPORT.md` (v3). This plan does **not** re-recommend already-shipped work
> (entailment NLI, conflict flags, span citations, mid-loop reading, coverage ledger, model ladder, SSRF
> guards, uncapped/responsive risk locked by tests) — it builds on them.

---

## 1. Executive Summary

ATHENA already does the hard part — an entailment NLI judge, cross-source conflict detection, URL-liveness,
span citations, and an uncapped/responsive risk formula locked by tests. The gap to a stable
Perplexity/Gemini-grade standard is **three things, in this order**:

1. **Honesty of the number (P0).** The reported hallucination risk is biased downward: the verifier edits
   out bad claims *before* measurement (`graph.py:_run_research_inner` line 471 → 480-486), NEI is
   discounted 60% (`entail.py:NEI_WEIGHT`), conflicts + dead citations are computed but never scored, and a
   cosine-only fallback is presented as a full verdict (`TrustPanel.tsx:TrustSummary`). Until this is fixed,
   "<10%" is partly self-certification.
2. **Reduce-at-source (P0/P1).** Citations are *requested* but never *enforced* at write time
   (`synthesizer.py:SYS`); the grounding test is cosine ≥ 0.55, not entailment (`guard.py:factcheck`); the
   retriever is a 384-dim English-only encoder (`embed.py`). CRAG/Self-RAG-style write-time grounding + an
   NLI support test + a stronger retriever are what drive the *true* rate under 10%.
3. **Make trust visible and runs reliable (P1/P2).** Per-claim verdicts are persisted but never shown; a DB
   blip at the finish line shows "Done" over a blank report; SSE has no resume.

**The governing rule of this plan (do not violate):** we make the metric *more honest first* — which may
push the reported number **above 10% on some runs** — then we drive the true rate down with grounding until
the honest number is under 10%. We never cap, clamp, floor, or discount the metric to hit the target. This
extends the already-locked "risk is uncapped and responsive" tests.

---

## 2. Engineering principles & guardrails

- **Honest-first.** Every measurement change must keep the existing `test_risk_is_uncapped_and_responsive`
  and `test_entail_judge_is_model_agnostic` green. The honest aggregate is computed at the **orchestration
  layer** (`graph.py` / a new `quality.aggregate_risk`), leaving the tested `entail_report` formula intact.
- **Preserve public signatures.** Extend with optional keyword args; never break `entail_report`,
  `factcheck`, `quality_score`, `build_evidence`, `synthesize_sections`, `for_role`.
- **Test-locked.** Each item ships with new deterministic tests; backend suite must stay ≥ current count
  (312) with 0 failures; frontend `tsc --noEmit` exit 0 + `vitest run` green.
- **No new secrets in code; no surprise runtime deps.** Model/infra changes (BGE-M3, durable queue) are
  flagged with their migration cost and gated behind config.
- **Behind flags where risky.** Reference-free re-check and write-time "cite-or-cut" run in deep/patient
  mode first, measured against eval before becoming default.

---

## 3. Evidence base (why these levers)

| Lever | Finding from research | Source |
|---|---|---|
| Write-time grounding + refusal on weak context | CRAG/Self-RAG reach ~0.97 fact-check accuracy; RAG cuts hallucination 42–68% | [CRAG](https://www.emergentmind.com/topics/corrective-retrieval-augmented-generation-crag), [arXiv 2505.09031](https://arxiv.org/abs/2505.09031) |
| Reference-free re-verification | Chain-of-Verification drafts → verification questions → revise, materially lifts factuality | [galileo](https://galileo.ai/blog/mastering-rag-llm-prompting-techniques-for-reducing-hallucinations) |
| Honest faithfulness measurement | RAGAS faithfulness (reference-free) + ALCE citation precision/recall (cited docs must *entail* the sentence); report span-level so macro metrics don't mask pseudo-citations | [langcopilot](https://langcopilot.com/posts/2025-09-17-rag-evaluation-101-from-recall-k-to-answer-faithfulness), [arXiv 2507.18910](https://arxiv.org/pdf/2507.18910) |
| Retrieval ceiling | 2026 self-hosted default BGE-M3 (100+ langs, dense+sparse+multi-vector) + BGE-reranker-v2 | [ailog](https://app.ailog.fr/en/blog/guides/choosing-embedding-models), [FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) |
| Inline sentence-level citations | Correlate with lower hallucination than paragraph-level (Perplexity vs Gemini) | [clickittech](https://www.clickittech.com/ai/perplexity-deep-research-vs-openai-deep-research/) |

---

## 4. Phase P0 — ULTRA-HIGH: make "<10%" real and trusted

### P0-1 — Honest hallucination aggregate. (Effort M · Impact High)

**Objective.** The reported `hallucination_risk` reflects what the model actually produced — counting
unsupported claims at full weight, the verifier's edits as hallucination events, and folding conflicts +
dead citations in — measured on the **pre-verifier** report.

**Current state.** `graph.py` runs `verify_report` (line 471, mutates `markdown`), then `factcheck` (480) and
`entail_report` (486) measure the *edited* text; `risk = ent["risk"]` (491) uses `(refuted + 0.4·nei)/total`
(`entail.py:261`); `conflicts`/`dead_links` only become flag strings (528-531).

**Implementation.**
1. In `_run_research_inner`, capture `markdown_pre = markdown` immediately after `synthesize_sections` and
   `strip_invalid_citations` (see P0-2 for the move), **before** `verify_report`.
2. Run `factcheck` and `entail_report` on `markdown_pre`. Keep `verifier_contested` (count of corrected +
   dropped sentences) from `verify_report`.
3. Add `quality.aggregate_risk(ent, g, *, conflicts, dead_citations, corrections, total_claims) -> dict`
   returning `{"risk": float, "components": {...}, "honest": True}`:
   ```python
   # NEI counts at (near) full weight; conflicts and dead citations are real defects.
   numer = ent["refuted"] + NEI_FULL*ent["nei"] + W_CONFLICT*conflicts + W_DEAD*dead_citations + corrections
   risk  = min(numer / max(total_claims, 1), 1.0)   # min() bounds a fraction, NOT a cap on a sub-1 value
   ```
   `NEI_FULL` defaults to ~0.8–1.0 (config), `W_CONFLICT`/`W_DEAD` ~0.5 each, `corrections` adds to both
   numerator and denominator. `entail_report` is **unchanged** (its tested 0.4-blend stays as a component
   signal we can still display).
4. `graph.py` uses `aggregate_risk(...)["risk"]` as the reported `risk`; persist both the honest risk and
   the entail-component risk in the `trust` ledger for transparency.

**Tests.** New `tests/test_aggregate_risk.py`: all-refuted → ≥0.9; all-supported, no conflicts/dead →
0.0; adding a conflict or a dead citation strictly raises risk; a verifier correction strictly raises risk;
NEI contributes more than the old 0.4 blend. Existing entail tests stay green (formula untouched).

**Acceptance.** On a fixture report with 1 refuted + 2 NEI + 1 conflict + 1 dead link, the reported risk is
demonstrably higher than today's `(1 + 0.4·2)/N`, and the `trust` row shows the component breakdown.

**Decision required (flag before coding).** Raising NEI weight conflicts with
`test_nei_counts_less_than_refuted_toward_hallucination_risk` *if* applied inside `entail_report`. We avoid
that by aggregating at the orchestration layer; `entail_report` keeps NEI < refuted. Confirm we keep the
blended entail number as a secondary display, with the aggregate as the headline.

**Risk/rollback.** Pure additive at orchestration layer; behind a `HONEST_RISK=1` config default-on, flip
off to restore prior behavior.

### P0-2 — Write-time claim grounding (cite-or-cut). (Effort M · Impact High — biggest reduce-at-source lever)

**Objective.** Every factual sentence in the shipped body carries a valid in-range `[n]`; uncited/invalid
ones are hedged or removed before persist, and counted.

**Current state.** `synthesizer.py:SYS` (9-23) *asks* for citations and "insufficient evidence" but nothing
enforces it; `strip_invalid_citations` (38-43) only removes out-of-range markers (leaving the sentence as
uncited prose); `guard.factcheck` already treats uncited/out-of-range as unsupported (38-43) but only
*after* the report ships. `entail_report.cited_sentences` (74-91) ignores uncited sentences entirely.

**Implementation (two layers, ship layer A first).**
- **A. Deterministic gate (S).** New `guard.enforce_grounding(markdown, n_sources) -> (markdown, report)`:
  reuse `_sentences`; for each body sentence (excluding headings, list framing, and the `_META`/
  `_ABOUT_SOURCES` patterns already in `entail.py`) that asserts a fact but lacks a valid in-range `[n]`,
  tag it for the metric and mark it inline (e.g. a trailing `⚠ uncited`), returning the count. Call it in
  `graph.py` right after `strip_invalid_citations`. Feed the uncited-claim count into `aggregate_risk`
  (P0-1) so uncited fabrications cost risk.
- **B. LLM cite-or-cut revision (M, deep/patient mode first).** New `agents/reground.py:reground(markdown,
  evidence, llm)`: for each flagged sentence, ask the model to either attach a correct `[n]` from the
  evidence or rewrite it as hedged/removed — a CRAG/Self-RAG-style corrective pass. Re-run
  `enforce_grounding` after to confirm zero uncited factual sentences remain.
- **C. Ordering fix.** Move `strip_invalid_citations` to run **before** `verify_report`/`factcheck`/`entail`
  (today it's at `graph.py:475`, after verify at 471) so fabricated markers are counted, not silently
  dropped.

**Tests.** `tests/test_enforce_grounding.py`: a report with an uncited factual sentence → flagged + counted;
a fully-cited report → zero flags; headings/framing never flagged; out-of-range `[n]` treated as uncited.

**Acceptance.** Post-gate, no body sentence asserts a fact without a valid `[n]` (layer B) or every such
sentence is visibly marked and counted (layer A); the aggregate risk reflects them.

**Risk/rollback.** Layer A is non-destructive (marks, doesn't delete). Layer B behind a flag; if a rewrite
fails entailment it is reverted to a hedge, never silently dropped.

### P0-3 — NLI as the support test + honest fallback. (Effort M · Impact High)

**Objective.** Entailment is the support decision; cosine is only a candidate pre-filter; a degraded
(cosine-only) run never reports a confident "<10%".

**Current state.** `guard.factcheck` decides support by cosine ≥ 0.55 (`guard.py:12,47`); `entail_report`
falls back to symmetric cosine when coverage < 0.5 or no model (`entail.py:228-229`), and `graph.py:491`
then uses that cosine risk as if equivalent.

**Implementation.**
1. In `graph.py`, set `degraded = ent["engine"] != "entailment"`. When degraded: (a) do **not** present the
   number as a verified <10% — `aggregate_risk` adds a `degraded` penalty band / floor and sets
   `trust["assurance"]="reduced"`; (b) retry `entail_report` once on a smaller batch before falling back.
2. Use cosine strictly as a pre-filter inside the entailment path (gate which claims need the NLI call), not
   as the final verdict; raise the cosine `threshold` when it is the *only* signal.
3. Plumb `degraded`/`assurance` and `engine` into the `trust` ledger and the `entail`/`quality` SSE events.

**Tests.** `tests/test_degraded_assurance.py`: engine=="embedding" → `trust["assurance"]=="reduced"` and the
reported risk is not presented as a confident pass; engine=="entailment" → full assurance.

**Acceptance.** A run where the judge didn't cover ≥50% of claims is labeled reduced-assurance end to end.

### P0-4 — Close the two trust cliffs (blank report; degraded shown as verified). (Effort S–M · Impact High)

**Objective.** Never show "Done" over a blank report; never present a cosine-only run as fully verified.

**Current state.** `persist_report` failure is caught/logged (`graph.py:551-555`) but `done` fires anyway
(564) → frontend `getRun` returns null → blank "Report" (`page.tsx:45-49`). `TrustPanel` shows the
"Entailment NLI / N claims checked" tag and the "none were left unsupported" all-clear regardless of engine
or whether any claim was checked (`TrustPanel.tsx:51,83-86`).

**Implementation (backend).**
1. Track `persist_ok` from `persist_report`. Emit `done` with `report_ready: persist_ok`; on failure emit a
   distinct `report_unavailable` payload **and** include the synthesized `markdown` + `quality` inline in
   the event so the UI can render from memory even if the DB read fails. Retry `persist_report` once on
   failure before giving up (`persist.py`).
**Implementation (frontend).**
2. `TrustPanel.tsx`: when `trust.engine !== "entailment"` render a `Degraded: similarity-only grounding — no
   per-claim NLI verdicts` banner; gate the "none were left unsupported" all-clear (83-86) on
   `engine === "entailment" && total > 0`, else show "Not independently verified."
3. `page.tsx`: on `phase==="done"` retry `getRun` with backoff; if still null, render from the inline
   payload (step 1) or an explicit error card with Retry (mirror `ANTIGRAVITY_REPORT.md` F10).

**Tests.** Frontend `vitest`: TrustPanel with `engine:"embedding"` shows the degraded banner and no
all-clear; with `engine:"entailment", total:0` shows "not verified". Backend: persist-failure path emits
`report_ready:false` (mock `persist_report` to raise).

**Acceptance.** Forced persist failure → UI shows the report (from inline payload) or a clear error, never a
blank "Done"; cosine-only run is visibly labeled degraded.

---

## 5. Phase P1 — HIGH: drive the true rate down & make trust visible

### P1-1 — Upgrade the retrieval stack (BGE-M3 + BGE-reranker-v2). (Effort M · Impact High)
**Where.** `embed.py:_get_model` (line 10, `bge-small-en-v1.5`), `_get_reranker` (37, MiniLM-L-6),
`_QUERY_PREFIX` (4). **Steps:** (1) verify `fastembed` supports `BAAI/bge-m3` + a `bge-reranker-v2` cross
encoder; if not, add a hosted-embedding fallback behind config. (2) Swap models; adjust `_QUERY_PREFIX`
per bge-m3 guidance. (3) **Migration (hard dependency):** the pgvector embedding dim changes (384→1024),
which breaks stored `memory`/recall vectors — add a migration that re-creates the embedding column at the
new dim and re-embeds or version-gates old rows; **include the model name+version in all embedding cache
keys** (`cache.py:skey`, P3-overlap) so stale 384-dim vectors are never mixed in. (4) Widen the rerank
candidate set beyond `items[:48]` (`rag.py:99`) and rank **all** chunks rather than `chunk_text(text)[:8]`
(`rag.py:81`) — pre-score cheaply, then rerank the wider candidate pool. **Tests:** embedding dim assertion;
`build_evidence` returns chunks from beyond position 8 when those are most relevant (fixture). **Risk:**
model download size/latency; gate behind config and benchmark on eval before default-on.

### P1-2 — Ground-check against the evidence actually shown. (Effort S · Impact High)
**Where.** `guard.factcheck` re-chunks only `min(len,6000)` chars of raw sources (`guard.py:26`). **Steps:**
add optional `evidence_chunks: dict[int,list[str]] | None` to `factcheck`; when provided, embed those exact
chunks (the text `build_evidence` sent to the writer) instead of re-chunking prefixes. `graph.py` passes the
per-source chunk map already available from synthesis. **Tests:** a claim supported by text at char 8000 of a
long source is scored supported when its evidence chunk is supplied (today it false-NEIs). **Risk:** none;
signature is back-compatible (default re-chunk path preserved).

### P1-3 — Rerank/select on fetched full content, not title+snippet. (Effort S–M · Impact High)
**Where.** `relevance.filter_by_relevance` scores `title+snippet` (`relevance.py:50`); evidence fallback uses
snippets (`graph.py:413-416`). **Steps:** after `_read_top`, add a content-aware re-score in `graph.py`
before `select_sources` — `rerank(topic, content_excerpt)` for entries that have `content`; prefer fetched
`content` over snippet in the `build_evidence`-empty fallback. **Tests:** an entry with a generic snippet but
on-topic body ranks above a clickbait-snippet entry. **Risk:** extra rerank cost on the read set; bounded by
`POOL_CAP`.

### P1-4 — Reference-free re-verification of top claims (CoVe/CRAG corrective). (Effort M · Impact High)
**Where.** New `agents/recheck.py:recheck_claims(claims, topic, llm, search) -> list[verdict]`. **Steps:**
take the top-K highest-risk claims from `entail_report.verdicts`, generate a neutral verification query per
claim, run a fresh search (reuse `multi_search`), fetch + entail the claim against the *fresh* sources; if
fresh evidence refutes a claim the cited source "supported," raise risk and flag "cited-but-wrong." Gate
behind deep/patient mode. **Tests:** mock search returning a contradicting fresh source flips a claim to
refuted. **Risk:** latency/cost — gated, K small, behind eval validation.

### P1-5 — Fix the dedup/content key mismatch. (Effort S · Impact High — silent grounding hole)
**Where.** `select.dedup_near` returns a normalized key that can diverge from `e["hit"].url` used by
`assemble_content`/`build_evidence` (`select.py:91-113`, audit Group-2 #6). **Steps:** verify the key path
end to end; standardize on one key (prefer the original `all_hits` key) or normalize consistently
everywhere; tag content provenance (full vs snippet) and down-weight snippet-only sources for substantive
claims. **Tests:** regression — a selected source always resolves to its fetched content (no empty
assembly). **Risk:** low; add the test first to prove the bug, then fix.

### P1-6 — Recency / freshness handling. (Effort M · Impact Med-High)
**Where.** `graph._fanout_search` (209) appends only a hardcoded English authority hint; no date filtering.
**Steps:** detect time-sensitive intent (topic contains year/"latest"/"current"/release/pricing); add a
per-provider recency path (Tavily/Serper date params, SearXNG `time_range`, DDG sort) and a recency signal
into selection (extract dates from `trafilatura` metadata / `Last-Modified` / JSON-LD). **Tests:** a
time-sensitive topic produces a recency-filtered query variant. **Risk:** provider-specific params; degrade
gracefully when unsupported.

### P1-7 — Surface the per-claim verdict table + conflicts (data already persisted). (Effort M · Impact High)
**Where.** `persist_claims` already writes verdicts to `claims` (`persist.py:17-28`); `trust.conflict_items`
is computed (`graph.py:540`) but the UI shows only aggregates. **Steps:** add `GET /research/{id}/claims`
(`runs.py`) returning `[{text, verdict, confidence, conflict}]`; add a `ClaimsTable`/`ConflictsList`
component and link each claim to its citation passage (you already have real excerpts via `select_span`);
render `conflict_items` in `TrustPanel`. **Tests:** vitest for the table; backend test for the endpoint
shape. **Risk:** none; read-only surface.

### P1-8 — Provider robustness (429/Retry-After, surface drops). (Effort S–M · Impact Med-High)
**Where.** `search/registry.py:_safe` (22-34) and `providers.py` turn timeouts/429 into `[]` silently.
**Steps:** honor `Retry-After`/exponential backoff for 429; distinguish timeout from hard failure; emit a
`provider_health` field in run metadata so dropped providers are visible. **Tests:** a 429 then success is
retried; a hard 404 is not. **Risk:** added latency on throttle; bounded retries.

---

## 6. Phase P2 — MEDIUM: depth, integrity, eval, modality

| ID | Item | Where | Steps (concise) | Effort | Tests |
|---|---|---|---|---|---|
| P2-1 | Section-write retry/escalation | `synthesizer.synthesize_sections:290-307` | Reuse the shrink/escalate retry loop from `synthesize` (112-160); on `finish_reason=="length"` raise `max_tokens` and retry; surface failed-section count in trust | S | empty/length section retries, not silent placeholder |
| P2-2 | Prompt-injection hardening | `synthesizer.py:114-118`, `graphmem.py`, `memory.py` | Strip/escape the `«…UNTRUSTED…»` delimiter tokens from scraped text before embedding; prefer a structured (JSON) evidence channel | M | a source containing the END marker can't break out |
| P2-3 | Grounding gates the score | `quality.quality_score:11-19` | Multiplicative penalty/cap when `refuted>0` or dead links exist, instead of flat additive 30 | S | refuted>0 strictly lowers score beyond the additive term |
| P2-4 | Validator authority allowlist | `validator.score_source:54` | Require registered-domain match; `docs.`/`/docs` only a modifier on a recognized host, not a standalone tier | S | `docs.spam-blog.com` not scored authoritative |
| P2-5 | SSE resume + reconnect + per-run token | `events.py:55-76`, `runs.py:99-110`, `sse.ts` | Emit SSE `id:`; honor `Last-Event-ID`; manual reconnect on CLOSED; per-run stream capability vs one global token | M | resume from last id; multi-tab no double-replay |
| P2-6 | PDF/table-aware extraction | `fetch.py` | Content-type sniff → layout parser (marker-pdf/LlamaParse-class); capture tables/`figcaption`/`img[alt]` | M | a PDF with a results table yields the table text |
| P2-7 | Eval at scale (RAGAS + ALCE) | `eval/harness.py`, `eval/race.py` | Add reference-free faithfulness + ALCE citation precision/recall; independent judge; regression gate (fail if faithfulness drops / risk rises); expand `topics.py` to a tagged multi-domain set | M | harness prints `risk=.. q=.. faith=.. cite_p/r=..` |
| P2-8 | Honest corroboration / hop trust gate | `guard.py:55`, `hop.py:151` | Cluster sources by domain/content before counting `consensus`; gate unvalidated hop pages behind a trust floor | S–M | syndicated copies don't inflate consensus |

---

## 7. Phase P3 — LOW: polish, correctness, robustness

Batch as one cleanup PR; each is ≤S.

- Charset-aware HTML decode (`fetch.py:148`); absolute score floor under `min_keep` so a wholly off-topic
  batch isn't force-fed 5 sources (`relevance.py:58,64`); soft-404/parked detection in urlhealth
  (`urlhealth.py:32`); render unknown `[n]` as "unverified citation" and disable dead-link anchors
  (`ReportView.tsx:11`, `SourceList.tsx:34`, `CitationChip.tsx`); 404 (not placeholder body) on empty report
  export (`runs.py:144-158`); key-test without spending provider tokens (`app.py:121`); embedding
  model+version in cache keys (`cache.py:18` — overlaps P1-1); HTML-parser link extraction in multi-hop
  instead of regex (`hop.py:26`); share claim-filtering between `verifier` and `entail`
  (`verifier.py:29` vs `entail.py:86`).

---

## 8. Sequencing & milestones

**Milestone A — Trust Integrity (P0-1…P0-4).** *Exit:* reported risk is honest (pre-verifier, NEI full
weight, conflicts/dead/corrections folded, uncited counted); degraded runs labeled; no blank-report cliff.
Backend suite green + new aggregate/grounding/degraded tests; frontend tsc+vitest green. *This is the gate
before any "<10%" claim is credible.*

**Milestone B — Grounding Quality (P1-1…P1-5).** *Exit:* BGE-M3 + wider rerank live (with migration);
checker reads the shown evidence; selection re-ranks on full content; reference-free re-check catches
cited-but-wrong; dedup key bug fixed with a regression test. *Drives the true rate down.*

**Milestone C — Visibility & Proof (P1-6…P1-8, P2-5, P2-7).** *Exit:* recency handling; per-claim ledger UI
+ conflicts; provider health; SSE resume; eval harness reports RAGAS faithfulness + ALCE citation
precision/recall with a regression gate. *Proves <10% holds across models over time.*

**Milestone D — Depth, integrity, modality (P2-1…P2-4, P2-6, P2-8) + P3.** As capacity allows.

Run the full backend `pytest` and frontend `tsc --noEmit` + `vitest run` at the end of every milestone; do
not advance a milestone with a red suite.

---

## 9. Testing & measurement strategy

- **Deterministic (every PR):** new unit tests per item (named above), backend suite ≥ 312 with 0 failures,
  frontend `tsc --noEmit` exit 0 + `vitest run` green. Locked tests `test_risk_is_uncapped_and_responsive`
  and `test_entail_judge_is_model_agnostic` must stay green throughout.
- **Faithfulness (Milestone C):** extend `eval/harness.py` with RAGAS-style reference-free faithfulness and
  ALCE citation precision/recall; record per-run `risk / faithfulness / citation-precision / citation-recall`
  and gate regressions. Run two models (e.g. a fast and a stricter model) to prove the number is
  model-agnostic, matching `for_role("entail", …)` routing.
- **The <10% claim is earned, not asserted:** it is valid only when the *honest* aggregate (P0-1) is < 0.10
  on the eval set with a non-degraded engine — never by tuning weights to hit the target.

---

## Appendix — coverage & file map

Backend touched across phases: `agents/graph.py` (orchestration order, honest aggregate, degraded plumbing,
done/report-ready), `agents/quality.py` (`aggregate_risk`, score gating), `agents/guard.py`
(`enforce_grounding`, evidence-aligned factcheck, NLI-as-decision), `agents/entail.py` (one-retry fallback,
shared claim filter), `agents/synthesizer.py` (section retry, injection hardening), `agents/reground.py`
(new, cite-or-cut), `agents/recheck.py` (new, reference-free), `agents/verifier.py`, `agents/persist.py`
(retry + report_ready), `agents/validator.py`, `agents/hop.py`, `embed.py` + `rag.py` (retrieval upgrade,
wider rerank, all-chunk ranking), `search/relevance.py`, `search/registry.py`, `search/providers.py`,
`fetch.py` (PDF/tables, charset), `cache.py` (model-versioned keys), `api/runs.py` + `api/events.py`
(claims endpoint, SSE resume, per-run token), `eval/harness.py` + `eval/race.py` + `eval/topics.py`.
Frontend: `components/report/TrustPanel.tsx`, `ReportView.tsx`, `SourceList.tsx`, `CitationChip.tsx`,
new `ClaimsTable`/`ConflictsList`; `app/page.tsx`; `lib/sse.ts`, `lib/api.ts`, `lib/types.ts`. Plus one
pgvector dim migration for P1-1.

*All `file:symbol` references verified against the current tree. Companion: `RESEARCH-QUALITY-AUDIT-2026-06.md`
(findings) and `ANTIGRAVITY_REPORT.md` (correctness/security baseline).*
