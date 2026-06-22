# ATHENA Technical Audit & Gap Analysis Report (v4)

**Auditor:** Principal AI Research-Systems Engineer
**Method:** Exhaustive read of every backend + frontend file (parallel subsystem audits: agents, retrieval, API/infra/eval, UI), benchmarked against Gemini Deep Research, Perplexity Deep Research, and ChatGPT/OpenAI Deep Research (o-series). Every finding cites a real `file:symbol`. **Current test baseline: backend 384 passed, frontend `tsc --noEmit` clean + 55 vitest passed.**

> **What changed since v3 (this is the up-to-date state).** Most v3 findings have been **closed** by two programs of work: (1) the 5-improvement deep-research upgrade — **mid-loop reading + coverage ledger, multi-hop citation chasing, section-by-section synthesis, adaptive planning, model ladder, GraphRAG**; and (2) the **trust & research-quality overhaul (Milestones A–D)** which made the hallucination metric *honest* and the pipeline higher-quality. Sections 1–3 below have been rewritten to current reality; §4 (the original v3 FIX/CHANGE/NEW list) is kept as **historical record** and is superseded by the **§3.5 findings-status table**. Companion docs: `docs/RESEARCH-QUALITY-AUDIT-2026-06.md`, `docs/RESEARCH-QUALITY-EXECUTION-PLAN.md`, `docs/RESEARCH-QUALITY-ROADMAP.md`.
>
> **What landed in Milestones A–D:** honest risk aggregate (pre-verifier, NEI near-full weight, + conflicts/dead-links/verifier-corrections/uncited); write-time claim-grounding gate; NLI as the support decision with an honest cosine-only fallback (reduced-assurance + uncertainty floor); no blank-report cliff (persist retry + inline fallback + degraded-run UI disclosure); evidence-aligned factcheck; content-aware reranking + config-gated retriever + all-chunk ranking; reference-free re-verification; per-claim verdict ledger UI; recency-biased retrieval; provider 429/Retry-After backoff; SSE id/Last-Event-ID resume + reconnect; RAGAS-faithfulness + ALCE citation precision/recall + a regression gate; section-write retry; prompt-injection fence hardening; grounding gates the quality score; validator authority allowlist; PDF layout-aware extraction; domain-clustered corroboration; hop trust gate.

---

## 1. Executive Summary (v4 — current)

ATHENA has a top-tier retrieval/RAG core **and** a real agentic depth layer **and** an honest, auditable trust layer. The v3 "one architectural gap from real deep research" and the trust/measurement holes are **closed**:

- **Research depth — RESOLVED.** ATHENA reads sources **mid-loop** (`graph._read_top` → reflect/refine see real content), maintains a sub-question × entity **coverage ledger** that drives drill/expand/stop, and follows citations to primaries via **multi-hop chasing** (`hop.py`, now behind a trust gate). Synthesis is section-by-section with globally consistent `[n]` citations.
- **Trust / honesty — RESOLVED (the differentiator).** Grounding is **directional entailment** (Supported/Refuted/NEI), not bare cosine; the reported hallucination risk is **honest** — measured on the *pre-verifier* report, NEI near-full weight, with cross-source conflicts, dead/fabricated citations, verifier corrections, and **uncited** claims folded in, and a **cosine-only fallback is disclosed as reduced-assurance** (uncertainty floor) instead of faking a low number. Claim grounding is enforced at write time; a per-claim **verdict ledger** is exposed in the UI; and a **RAGAS-faithfulness + ALCE citation-precision/recall** eval with a **regression gate** exists to prove it over time.
- **Safety — hardened.** SSRF is guarded (manual redirect re-validation + DNS-rebind peer-IP check), prompt-injection fences are neutralized in every untrusted-text path, the API is behind a shared-token gate, and inputs/endpoints are parameterized (no SQLi). An independent correctness+security review of the latest work found **no CRITICAL/HIGH issues**.

**What remains (honest, capability/scale — not correctness or trust holes):** code interpreter / quantitative analysis (❌); image/figure *understanding* (PDF text **and tables** are now extracted; images are still dropped); **multi-tenant** auth + per-run/per-user keys (a shared-token gate exists; per-run token deferred); a **durable queue + Redis event bus** (still in-process; SSE now resumes/reconnects); server-backed history + follow-up.

Verdict: production-grade trust + agentic depth; the open items are capability breadth (code/vision), multi-tenancy, and durable orchestration.

---

## 2. Architecture Assessment

### Strong (keep; only refine)
- **Reflective autonomy** — `controller.py:reflect` (stop/drill/continue), now reliable on reasoning models after the `max_tokens` fix.
- **Two-model verification** — `verifier.py:verify_report` independently checks each cited claim; proven live (28 corrections on a weak draft).
- **Precision retrieval + span citations** — `rag.py:build_evidence` (embed → cross-encoder rerank → type-diverse) + `rag.py:select_span`.
- **Cross-run memory** — `memory.py:remember/recall` over pgvector (HNSW), with a similarity floor.
- **Role-based model routing** — `graph.py` `fast = llm_fast or llm`; strong model reserved for synthesis.

### Previously weak — now RESOLVED (v4)
- **Mid-loop reading** — ✅ `graph._read_top` fetches the round's top sources so reflect/refine reason over real content; a sub-question × entity **coverage ledger** (`coverage.py`) drives drill/expand/stop. (Was the root-cause depth gap.)
- **Faithfulness** — ✅ directional **entailment** (`entail.py`: Supported/Refuted/NEI) supersedes bare cosine; cosine is a candidate pre-filter only, and is raised + disclosed as *reduced-assurance* when it's the sole signal. Cross-source **consensus** counts DISTINCT domains (`guard._domain`) so mirrors can't fake agreement.
- **Honest measurement** — ✅ `quality.aggregate_risk` is the headline: pre-verifier, NEI near-full, + conflicts/dead-links/verifier-corrections/uncited; grounding **gates** the quality score (`quality_score` multiplicative penalty).
- **Trust scoring** — ✅ `validator.py` tiers by **registered-domain** allowlist (no substring spoofing; `docs.`/`/docs` is a modifier, not a grant) + recency signals + query-side recency bias (`select.recency_query`).
- **Eval** — ✅ harness reads `quality_score` from `research_runs` (the broken-column bug is gone) and adds **faithfulness + citation precision/recall + a regression gate** (`eval/metrics.py`, `eval/harness.regression_gate`).

### Still weak / open (v4)
- **Single-process, single-tenant** — `runs.py` fire-and-forget `asyncio.create_task`; `events.py:EventBus` in-process (SSE now resumes/reconnects via `Last-Event-ID`, but a **durable queue + Redis bus** for >1 worker / restart survival is still open). Auth is a **shared token** (`auth.py`); **per-run/per-user keys + RLS** are deferred.
- **Modality / compute** — no code interpreter; image/figure understanding absent (PDF **text+tables** are extracted via pypdf layout mode, but figures/charts are not described).

---

## 3. Capability Gap Matrix

✅ solid · 🟡 partial/weak · ❌ absent.

| Capability | ATHENA (v4) | Gemini DR | Perplexity DR | ChatGPT DR |
|---|:---:|:---:|:---:|:---:|
| Reflective agent loop | ✅ `controller.py` | ✅ | ✅ | ✅ |
| **Mid-loop reading (read→re-query)** | ✅ `graph._read_top` + coverage ledger | ✅ | ✅ | ✅ |
| **Multi-hop citation chasing** | ✅ `hop.py` (trust-gated) | ✅ | ✅ | ✅ |
| Two-model claim verification | ✅ `verifier.py` | 🟡 | 🟡 | 🟡 |
| **Entailment / cross-source consensus** | ✅ `entail.py` + domain-clustered consensus | 🟡 | 🟡 | 🟡 |
| **Honest hallucination metric + per-claim ledger** | ✅ `aggregate_risk` + claims UI (a differentiator) | 🟡 | 🟡 | 🟡 |
| Span-level citations | ✅ `select_span` | 🟡 | ✅ | 🟡 |
| Cross-run memory | ✅ `memory.py` + GraphRAG (opt-in) | ✅ | 🟡 | ✅ |
| **Editable research plan (pre-run)** | ✅ `/api/plan` + editable UI | ✅ | 🟡 | ❌ |
| **Streaming report tokens / live `<think>`** | ✅ `stream_complete` + `report_delta`/`reasoning_delta` | ✅ | ✅ | ✅ |
| Source authority + recency weighting | ✅ tiered allowlist + `recency_query` | ✅ | ✅ | ✅ |
| **Prompt-injection / SSRF hardening** | ✅ fence-neutralized + redirect/peer-IP guards | ✅ | ✅ | ✅ |
| Faithfulness + citation eval + regression gate | ✅ `eval/metrics.py` (RAGAS + ALCE) | n/a | n/a | n/a |
| **Code interpreter / data analysis** | ❌ | 🟡 | ❌ | ✅ |
| **Multimodal (images/charts) + PDF read** | 🟡 PDF text+tables (pypdf layout); images ❌ | ✅ | 🟡 | ✅ |
| Server-backed history + follow-up | ❌ (localStorage, one-shot) | ✅ | ✅ | ✅ |
| **Auth / multi-tenant / per-user keys** | 🟡 shared-token gate; per-run/RLS deferred | ✅ | ✅ | ✅ |
| **Durable queue / multi-worker bus** | 🟡 in-process bus (SSE resumes); no durable queue | ✅ | ✅ | ✅ |

---

## 3.5 v3 findings — current status (v4)

✅ resolved · 🟡 partial / deferred · ❌ open. **This supersedes the per-item §4 list** (kept below as the original v3 audit, for historical record).

| v3 item | Status | Note |
|---|:--:|---|
| F1 eval harness broken | ✅ | reads `quality_score` from `research_runs`; + faithfulness/citation metrics (see C6) |
| F2 SSRF redirect / DNS-rebind | ✅ | manual per-hop re-validation + peer-IP check (`fetch.py`) |
| F3 prompt-injection unguarded | ✅ | fence delimiters neutralized in every untrusted path (`synthesizer._sanitize_untrusted`) |
| F4 negative results cached 24h | ✅ | empty/failed cached ~600s (`registry.multi_search`) |
| F5 citation fallback masks hallucinations | ✅ | uncited / out-of-range = unsupported; + write-time grounding gate (`guard.enforce_grounding`) |
| F8 relevance threshold empties set | ✅ | `min_keep` + absolute 0.15 floor (`relevance.filter_by_relevance`) |
| F10 UI empty report on failure | ✅ | `report_ready` + inline fallback + error card (`graph.py`/`page.tsx`) |
| F7 URL under-canonicalization | 🟡 | redirect-key-tolerant assembly added; base `url_hash` canonicalization unchanged |
| F6 RRF mutates input hits | 🟡 | not re-verified this cycle |
| F9 cancel doesn't truly cancel | ❌ | open |
| F11 citation popovers inaccessible | ❌ | open |
| C1 mid-loop reading + coverage ledger | ✅ | `graph._read_top` + `coverage.py` |
| C2 streaming + usage + reasoning | ✅ | `stream_complete`, usage box, `reasoning_delta` |
| C3 entailment + cross-source consensus | ✅ | `entail.py` + domain-clustered consensus (`guard._domain`) |
| C4 credibility + recency model | ✅ | tiered registered-domain allowlist + `select.recency_query` |
| C7 stop discarding long docs | ✅ | all-chunk ranking + wider rerank pool (`rag.build_evidence`) |
| C6 eval rigor | 🟡 | citation metric + regression gate ✅; a fixed independent judge still TODO |
| C5 query fan-out + specialists | 🟡 | fan-out + recency variant + specialist seeding; news/academic providers not added |
| C9 dedup + freshness | 🟡 | title-dedup + redirect-tolerance + recency; semantic/body-hash dedup TODO |
| C8 durable queue + Redis bus | ❌ | open (in-process bus; SSE now resumes/reconnects) |
| N1 editable research plan | ✅ | `/api/plan` + editable UI |
| N2 streaming tokens / reasoning trace | ✅ | live draft + reasoning trace |
| N5 multi-hop citation chasing | ✅ | `hop.py` + trust gate |
| N8 conflict reporting + claims persistence | ✅ | `persist_claims` + per-claim ledger UI + conflict display |
| N9 knowledge-graph memory | 🟡 | GraphRAG opt-in (`graphmem.py`) |
| N4 multimodal + PDF | 🟡 | PDF text+tables (pypdf layout mode); images/charts not described |
| N6 auth + per-user keys + RLS | 🟡 | shared-token gate; per-run/per-user keys + RLS deferred |
| N3 sandboxed code interpreter | ❌ | open |
| N7 server-backed history + follow-up | ❌ | open (localStorage) |
| N10 private-workspace integration | ❌ | open |

---

## 4. Prioritized Recommendations  *(original v3 audit — historical; see §3.5 for current status)*

> The FIX/CHANGE/NEW items below are the **original v3 audit** and are retained verbatim for traceability. Most FIX items and the core CHANGE/NEW depth+trust items are now **resolved** — consult §3.5 for the live status of each.

Effort **S** ≤½d · **M** 1–3d · **L** ≥1wk. Impact High/Med/Low.

### FIX — correctness & security bugs (verified)

**F1. Eval harness is broken — selects a non-existent column. (S, High)**
`eval/harness.py:run_eval` runs `select markdown, quality_score, quality_breakdown from reports`, but the `reports` table (`migrations/001_init.sql`) has no `quality_score` (it lives on `research_runs`/`eval_runs`) → `asyncpg.UndefinedColumnError`. The eval path cannot run. **Fix:** read `quality_score` from `research_runs` (join on `run_id`). You currently *cannot measure* whether any change helps.

**F2. SSRF via redirects / DNS-rebinding. (M, High)**
`fetch.py:_is_safe_url` validates the host, but `fetch_extract` then issues `httpx.AsyncClient(follow_redirects=True)` which re-resolves DNS and follows redirects **without re-validating** — a public host can 302 to `http://169.254.169.254/` (cloud metadata) or an internal IP. The `render_js_html` Playwright path loads subresources unvetted. **Fix:** pin the validated IP for the connection, validate every redirect hop, block metadata/link-local ranges explicitly, cap redirects.

**F3. Prompt-injection: fetched page text flows unguarded into the model. (M, High)**
`assemble_content`/`build_evidence` drop raw page text into the `synthesizer.py` user message (`EVIDENCE:\n{block}`) and the same excerpts into `verifier.py`. A malicious page ("ignore previous instructions…") is treated as content; there's no delimiting, spotlighting, or injection filter. **Fix:** wrap untrusted source text in explicit data-marked delimiters, instruct models to never follow instructions inside evidence, add a lightweight injection classifier/quarantine.

**F4. Negative results cached for 24h. (S, Med)**
`fetch.py:fetch_extract` caches empty extractions (`set_json(ck, text or "", ttl=86400)`) and `registry.py:multi_search` caches the merged result even when *every* provider failed — a transient outage poisons a query/page for a day. **Fix:** don't long-cache empties; short TTL (≤300s) for empty/failed.

**F5. Citation fallback masks hallucinations. (S, High)**
`guard.py:factcheck` — a sentence with no `[n]` (or an out-of-range `[n]`) falls back to `idxs = list(range(len(sources)))` and passes if it resembles *any* source. A fabricated, uncited claim is scored as supported. **Fix:** treat uncited factual claims and invalid `[n]` as unsupported-by-default.

**F6. `merge.py:rrf_merge` mutates input hits → non-idempotent / cache corruption. (S, Med)**
It writes `hit.rrf_score`/`hit.providers` onto the shared `SearchHit` objects (which `multi_search` also caches). **Fix:** operate on `dataclasses.replace` copies; never mutate inputs.

**F7. `base.py:url_hash` under-canonicalizes → duplicate sources. (S, Med)**
Only strips `#`, trailing `/`, lowercases. `www.`, `http`vs`https`, `utm_*`/`ref`/`gclid`, `m.`, and AMP variants all produce distinct keys, so the same article double-counts in RRF and eats two `per_doc_cap` slots. **Fix:** canonicalize host (drop `www.`/`m.`), scheme-insensitive key, strip tracking params, collapse AMP.

**F8. Relevance threshold can empty the candidate set. (S, High)**
`relevance.py:filter_by_relevance` keeps hits where `sigmoid(rerank_logit) ≥ 0.50` on noisy title+snippet text; borderline-but-real sources are dropped before they're ever fetched, with no floor. (This + F7 directly cap the low source counts you see, e.g. 17.) **Fix:** add a `min_keep` floor (keep top-N when too few survive) and prefer filtering on fetched full text.

**F9. Cancel doesn't actually cancel. (M, Med)**
`runs.py:cancel` sets a flag + DB row; the fire-and-forget task is never `.cancel()`-ed, and `graph.py` only checks `is_cancelled` between rounds — so a cancel during `fetch_many`/`synthesize`/`verify` keeps burning tokens. **Fix:** retain the task handle and `task.cancel()`; check cancellation between sub-steps.

**F10. UI shows an empty "Report" on failure/cancel. (M, High)**
`app/page.tsx` calls `getRun` whenever `stream.done` (set by `failed`/`cancelled` too), then renders the report section with `report=null` → blank "Report" heading; the failure message only lived transiently in `status`. **Fix:** track a discrete `phase: running|done|failed|cancelled`; render a dedicated error card with the message + Retry; show partial report on cancel.

**F11. Citation popovers are inaccessible. (M, Med)**
`components/report/CitationChip.tsx` opens on `onMouseEnter`/`onMouseLeave` (no keyboard/touch), clips at article edges, no `Escape`/aria. **Fix:** focus+click driven, `aria-expanded`/`describedby`, flip/portal so it never clips.

### CHANGE — existing logic too weak vs benchmarks

**C1. Read sources MID-LOOP + add a coverage ledger. (L, High) — the biggest quality lever.**
`graph.py:_run_research_inner`: fetch+extract a small top-k each round so `findings_text`/`reflect`/`refine` see real content; maintain a `ResearchState` (sub-question × entity → supporting evidence + confidence); route `drill` at the lowest-coverage cell. This is the architectural change that makes ATHENA actually "deep."

**C2. `gateway/llm.py:complete` — add streaming, usage/cost, and `reasoning_content`. (M, High)**
Today it returns only `choices[0].message.content`, discarding `resp.usage` (→ zero cost tracking) and `reasoning_content` (→ the empty-body workarounds). **Fix:** capture usage (persist per-run tokens/cost), add an `acompletion(stream=True)` path feeding the `bus`, and surface `reasoning_content` as a live trace.

**C3. Faithfulness: entailment + cross-source consensus, not bare cosine. (M, High)**
Extend `guard.py`/`verifier.py` to return entail/neutral/contradict (the verifier model already exists) and check each claim against ≥2 *independent* domains; surface "Sources [3][7] conflict on…". Cosine alone can't catch negation.

**C4. Real credibility + recency model. (M, High) — fixes Validation 0/22.**
`validator.py:score_source` uses substring host matching (so `github.com.phishing.io` scores high) and `build_evidence` leaves `trust=0.5` inert. **Fix:** registered-domain matching, a domain-authority table + low-quality blocklist, and a recency signal (extract dates from trafilatura metadata / `Last-Modified` / JSON-LD), feeding both selection and a new source-diversity term in `quality.py`.

**C5. Query fan-out + fold specialists + add engines. (M–L, High)**
`registry.py:multi_search` broadcasts one phrasing. Expand a topic into N sub-queries (entity/aspect/temporal) and RRF-merge the union. Critically, `specialist.py` (`arxiv_search`/`github_search`) returns bare dicts that are hand-wrapped only in `_seed_specialists` (round 1) and never join the main RRF pool — adapt them to `SearchHit` so academic/code breadth flows through RRF + relevance + trust. Add a news (GDELT/NewsAPI) and an academic (Semantic Scholar/Crossref) provider.

**C6. Eval rigor. (M, High)**
`eval/race.py:race_score` grades the report **with the same `llm` that wrote it** (self-preference bias). Use a fixed independent judge; add a citation-accuracy metric (reuse `guard.factcheck` aggregate); add a hard regression gate (fail if `race_overall` drops or `fact_risk` rises); expand `eval/topics.py` beyond its 3 AI topics to a tagged multi-domain set with gold citations.

**C7. `rag.py:build_evidence` — stop discarding long docs. (S, Med)**
`chunk_text(text)[:8]` keeps only the first ~8 chunks *positionally* before ranking, and `chunks_per=1` sends one chunk per source to the writer. **Fix:** embed-rank all chunks, keep top-N per doc by similarity, and raise `chunks_per` adaptively within the token budget.

**C8. Durable queue + Redis event bus. (M–L, High) — production spine.**
Replace `runs.py` fire-and-forget + `events.py` in-memory bus with a worker (arq/RQ on the provisioned Redis) and Redis pub/sub for SSE + cancel. Required for >1 worker, restart survival, and backpressure.

**C9. `select.py` dedup + freshness. (M, Med)**
`dedup_near` is title-word Jaccard (misses syndicated/reworded dups); `_freshness` is a year-substring in the URL. **Fix:** semantic/body-hash dedup post-fetch; real publication dates.

### IMPLEMENT NEW — capabilities ATHENA lacks

**N1. Editable research plan (plan → edit → execute). (M, High)** — signature Gemini DR feature. `POST /api/plan` returns + persists `{sub_questions, entities}`; UI renders an editable checklist; `/api/research` accepts the edited plan and seeds round 1 (the `round_start` event already carries `questions`). Files: `api/runs.py`, `agents/planner.py`, `agents/graph.py`, `app/page.tsx`, `lib/api.ts`.

**N2. Streaming report tokens + live reasoning trace. (M–L, High)** — pairs with C2; emit `report_delta` SSE, render progressively in `ReportView`; collapsible `<think>` from `reasoning_content`.

**N3. Sandboxed code interpreter. (L, High)** — the ChatGPT ADA gap. New `agents/tools/code.py` running Python in E2B or `docker run --network=none` (CPU/mem/time caps); emit tables/charts into the report. Gate behind auth (N6).

**N4. Multimodal + PDF extraction. (L, High)** — `fetch.py` is text-only via `trafilatura`; PDFs return garbage and images/charts are dropped. Content-type sniff → PDF/Office parser; capture `<figure>/figcaption`, `img[alt]`, Playwright screenshots → vision model descriptions before chunking.

**N5. Multi-hop citation chasing. (M–L, High)** — after extraction, harvest high-value outbound links, score with the reranker, queue a bounded second hop (reuse `_is_safe_url`+cache). How DR reaches primary sources.

**N6. Auth + per-user keys + RLS + rate/cost limits. (L, High) — production gate.** No auth on any route; `get_run`/`stream`/`cancel`/`report.pdf` accept a raw `run_id` (IDOR); `api_keys` PK is `provider` alone (one shared key set). Add Supabase Auth, `owner_id` + RLS on runs/sources/reports, composite `(owner_id, provider)` keys, per-identity rate limits and token/cost ceilings (needs C2). Make CORS origins configurable (hardcoded to `localhost:3000`).

**N7. Server-backed history + follow-up research. (L, High)** — `app/history/page.tsx` is localStorage and not reopenable. Add a runs list endpoint + `/run/[id]` viewer; add a follow-up composer that seeds a new run from the prior run's sources (the `memory`/`related` plumbing already exists).

**N8. Conflict/consensus reporting + claims persistence. (M, High)** — surface cross-source disagreement in the report (driven by C3); persist a `claims` table (claim, cited sids, verdict, score) — `persist.py:persist_report` currently passes `claims=[]` and drops all per-claim verdicts.

**N9. Knowledge-graph memory. (L, Med)** — `memory.py` stores one ~1200-char summary per run. Add per-source/per-claim rows (url, claim, embedding, trust, date) injected into the *retrieval* pool, then entity/relation triples for true cross-session reasoning.

**N10. Private workspace integration. (M, Med)** — a provider that indexes local files / Drive (OAuth) into the same RRF pipeline; enterprise research over private + public data.

---

## 5. Top 10 (strictly ordered by impact ÷ effort toward top-tier research)

1. **C1 — Mid-loop reading + coverage ledger.** The one change that makes ATHENA actually "deep"; root cause of weak reflect/refine.
2. **N1 — Editable research plan.** Highest-ROI UX leap toward Gemini DR; low risk.
3. **C4 — Real credibility + recency model.** Directly fixes the Validation 0/22 you keep seeing; lifts citation authority.
4. **F1 + C6 — Fix the (broken) eval + independent judge + citation metric.** You cannot improve what you cannot measure — and right now you can't measure at all.
5. **C2 + N2 — Streaming tokens + reasoning trace + usage/cost.** Biggest perceived-quality jump; unlocks cost guards.
6. **Security trio — F2 (SSRF) + F3 (injection) + N6 (auth/keys/RLS).** Can't be "top standard" while open to metadata-SSRF and cost-theft.
7. **C3 + N8 — Entailment/consensus + conflict reporting.** Real faithfulness beyond cosine; a genuine differentiator.
8. **C5 — Query fan-out + fold specialists + Bing/news/academic.** The breadth gap; the specialist-adapter fix is cheap and unlocks academic depth.
9. **N4 — Multimodal + PDF.** Removes structural blindness to images and the richest primary sources.
10. **N3 — Sandboxed code interpreter.** The quantitative-analysis gap vs ChatGPT (after auth lands).

*Just missed:* F5/F7/F8 (cheap correctness wins — do them in the NOW bucket), C8 (durable queue), N5 (multi-hop), N7 (history/follow-up).

---

## 6. Suggested Roadmap (v4 — current)

**DONE** (v3 NOW + most of NEXT, via the 5-improvement upgrade + Milestones A–D): F1/F2/F3/F4/F5/F8/F10 fixes · C1 mid-loop reading + coverage · C2 streaming + usage + reasoning · C3 entailment/consensus · C4 credibility + recency · C6 citation metric + regression gate · C7 all-chunk ranking · N1 editable plan · N2 streaming tokens · N5 multi-hop · N8 conflict reporting + claims persistence — **plus** the honest-measurement + write-time grounding + degraded-disclosure trust layer. Backend 384 / frontend 55 tests green.

**NOW (small, still open):** F9 real cancel · F11 accessible citation popovers · F6/F7 RRF-copy + URL canonicalization · urlhealth soft-404 detection · charset-aware decode · shared claim filter (`verifier`/`entail`).

**NEXT (measurability + capability):** C6 a fixed *independent* eval judge · the live `<10%`-across-models eval run (needs API key + DB) · C5 news/academic providers · SSE per-run stream token · `provider_health` in run metadata.

**LATER (scale + breadth):** N3 sandboxed code interpreter · N4 image/figure understanding (PDF text+tables already done) · N6 multi-tenant auth + per-user keys + RLS + rate/cost limits · C8 durable queue + Redis bus · N7 server-backed history + follow-up · C9 semantic/body-hash dedup · N9 deeper knowledge-graph memory · N10 private-workspace integration.

**The moat to protect:** verifiable, auditable trust — now honest end-to-end (pre-verifier measurement, NLI grounding, degraded-run disclosure, per-claim ledger, regression-gated eval). Don't trade it for breadth.

---

### Appendix — coverage
Every file under `services/api/athena/{agents,search,gateway,api,eval}`, plus `embed.py, rag.py, fetch.py, tokens.py, memory.py, cache.py, db.py, config.py, report/export.py`, all `migrations/*.sql`, `Dockerfile`, `docker-compose.yml`, `DEPLOY.md`; and `apps/web/{app/*, components/**, lib/*}`. Findings cross-checked by independent subsystem audits.

**v4 verification:** the trust/quality overhaul (Milestones A–D) was implemented test-first and reviewed by an independent correctness+security subagent pass — **no CRITICAL/HIGH issues** (SQLi, prompt-injection, SSRF, auth/IDOR, ReDoS, secrets all clean). Current baseline: **backend 384 passed, frontend `tsc` clean + 55 vitest passed.** Per-step detail in `docs/RESEARCH-QUALITY-ROADMAP.md`.
