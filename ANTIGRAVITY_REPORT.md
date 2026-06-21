# ATHENA Technical Audit & Gap Analysis Report (v3)

**Auditor:** Principal AI Research-Systems Engineer
**Method:** Exhaustive read of every backend + frontend file (4 parallel subsystem audits: agents, retrieval, API/infra/eval, UI), benchmarked against Gemini Deep Research, Perplexity Deep Research, and ChatGPT/OpenAI Deep Research (o-series). Every finding cites a real `file:symbol`.

> **What changed since v2.** v2 correctly named the big *capability* gaps (code interpreter, editable plan, multimodal). This v3 keeps those and adds what a line-by-line sweep found that v2 missed: **a broken eval harness, an SSRF redirect hole, unguarded prompt-injection, citation-fallback that masks hallucinations, non-idempotent RRF, and an open auth/key-theft surface.** Already-implemented features (reflective deep mode, two-model verifier, span citations, cross-run memory, fast/strong routing, report templates, patient mode, token budgeting, reranker relevance, JS-fetch fallback, Fernet-from-env, stale-run reconcile) are **not** re-recommended — only improved.

---

## 1. Executive Summary

ATHENA has a genuinely strong retrieval/RAG core and, after recent work, a real agentic layer (reflect/drill/stop, second-model verification, cross-run memory). But a full read shows it is **not yet "deep" in the Gemini/ChatGPT sense, and not yet safe to expose.** Two truths dominate:

- **Research-quality lever (the single biggest one):** ATHENA **never reads sources mid-loop.** `graph.py:_run_research_inner` does all fetching in one batch *after* every round finishes, so `controller.py:reflect` and `planner.py:refine` decide "drill vs stop" from titles + 200-char snippets only (`_round_digest`). The defining behavior of Gemini/ChatGPT DR — read → discover → re-query, and follow citations to primary sources — is absent. **Move fetching inside the round loop and add a coverage ledger + multi-hop link-chasing.** Everything else in "research depth" follows from this.
- **Production gate:** there is **no auth**, a **single global key vault** (any caller can use/steal another tenant's keys — `keys.py`, `api_keys` PK is `provider` alone), **IDOR** on every `run_id`, a **redirect-based SSRF** hole (`fetch.py`), and **unguarded prompt-injection** from fetched pages into the synthesizer. And the **eval harness is broken** (`harness.py` selects a non-existent column), so quality regressions are currently undetectable.

Verdict: a high-quality prototype with a top-tier retrieval core, one architectural gap from real "deep research," and several correctness/security holes that block both quality measurement and deployment.

---

## 2. Architecture Assessment

### Strong (keep; only refine)
- **Reflective autonomy** — `controller.py:reflect` (stop/drill/continue), now reliable on reasoning models after the `max_tokens` fix.
- **Two-model verification** — `verifier.py:verify_report` independently checks each cited claim; proven live (28 corrections on a weak draft).
- **Precision retrieval + span citations** — `rag.py:build_evidence` (embed → cross-encoder rerank → type-diverse) + `rag.py:select_span`.
- **Cross-run memory** — `memory.py:remember/recall` over pgvector (HNSW), with a similarity floor.
- **Role-based model routing** — `graph.py` `fast = llm_fast or llm`; strong model reserved for synthesis.

### Weak / divergent (grounded)
- **Linear pipeline, late reading** — `graph.py:_run_research_inner`: rounds do search→relevance→validate→persist, but `fetch_many`/`build_evidence` run once at the end. Reflection/refinement are blind to content. **Root cause of the depth gap.**
- **No source-state model** — research state is just `all_hits` (a URL dict) + free-text `findings_text`. No per-sub-question/per-entity coverage ledger, so "what do we still not know" is never computed.
- **Faithfulness is cosine-only** — `guard.py:factcheck` uses embedding cosine ≥ 0.55; cosine catches off-topic but not negation ("X improves Y" vs "X does *not* improve Y" embed nearly identically). No entailment, no cross-source consensus.
- **Trust is inert** — `validator.py:score_source` is a static substring allowlist; `rag.py:build_evidence` defaults `trust=0.5` for every web source and never *computes* it, so the trust term is effectively constant. This is why **Validation scores 0/22** on real runs.
- **Open, single-process, single-tenant** — `runs.py:start_research` fire-and-forget `asyncio.create_task`; `events.py:EventBus` in-memory (breaks at >1 worker, leaks queues); no auth anywhere.

---

## 3. Capability Gap Matrix

✅ solid · 🟡 partial/weak · ❌ absent.

| Capability | ATHENA | Gemini DR | Perplexity DR | ChatGPT DR |
|---|:---:|:---:|:---:|:---:|
| Reflective agent loop | ✅ `controller.py` | ✅ | ✅ | ✅ |
| **Mid-loop reading (read→re-query)** | ❌ (fetch is one late batch) | ✅ | ✅ | ✅ |
| **Multi-hop citation chasing** | ❌ | ✅ | ✅ | ✅ |
| Two-model claim verification | ✅ `verifier.py` | 🟡 | 🟡 | 🟡 |
| **Entailment / cross-source consensus** | ❌ (cosine only) | 🟡 | 🟡 | 🟡 |
| Span-level citations | ✅ `select_span` | 🟡 | ✅ | 🟡 |
| Cross-run memory | 🟡 `memory.py` (run-summary) | ✅ | 🟡 | ✅ |
| **Editable research plan (pre-run)** | ❌ | ✅ | 🟡 | ❌ |
| **Streaming report tokens / live `<think>`** | ❌ (report at `done`) | ✅ | ✅ | ✅ |
| **Code interpreter / data analysis** | ❌ | 🟡 | ❌ | ✅ |
| **Multimodal (images/charts) + PDF read** | ❌ (`trafilatura` text-only) | ✅ | 🟡 | ✅ |
| Source authority + recency weighting | ❌ (trust inert) | ✅ | ✅ | ✅ |
| Server-backed history + follow-up | ❌ (localStorage, one-shot) | ✅ | ✅ | ✅ |
| **Auth / multi-tenant / per-user keys** | ❌ | ✅ | ✅ | ✅ |
| **Prompt-injection / SSRF hardening** | ❌ / 🟡 | ✅ | ✅ | ✅ |
| Working regression eval | ❌ (broken query) | n/a | n/a | n/a |

---

## 4. Prioritized Recommendations

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

## 6. Suggested Roadmap

**NOW (days) — correctness, trust, safety; low risk**
F1 eval-column fix · F5 citation fallback · F7 url canonicalization · F8 relevance floor · F4 negative-cache TTL · F6 RRF copy · C4 credibility+recency · F2 SSRF redirect validation · F3 injection delimiting · F10/F11 UI error + accessible citations.

**NEXT (weeks) — the deep-research leap + measurability**
C1 mid-loop reading + N8 coverage/claims · N1 editable plan · C2+N2 streaming + usage + reasoning trace · C3 entailment/consensus · C5 query fan-out + specialist adapter · C6 eval rigor (independent judge, citation metric, gate, topics) · F9 real cancel.

**LATER (1–2 months) — capability + scale + multi-tenant**
N4 multimodal/PDF · N3 sandboxed code interpreter · N5 multi-hop chasing · N6 auth/RLS/limits · C8 durable queue + Redis bus · N7 server history + follow-up · C7/C9 chunking + dedup/freshness · N9 knowledge graph · N10 workspace integration.

---

### Appendix — coverage
Every file under `services/api/athena/{agents,search,gateway,api,eval}`, plus `embed.py, rag.py, fetch.py, tokens.py, memory.py, cache.py, db.py, config.py, report/export.py`, all `migrations/*.sql`, `Dockerfile`, `docker-compose.yml`, `DEPLOY.md`; and `apps/web/{app/*, components/**, lib/*}`. Findings cross-checked by four independent subsystem audits; the eval-column and reports-schema bug verified directly against `migrations/001_init.sql`/`004_eval.sql`.
