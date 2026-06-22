# ATHENA — Research Quality & Hallucination Audit (June 2026)

A full, file-by-file audit of the research engine (`services/api`) and UI (`apps/web`), cross-checked
against how the leading deep-research systems (Perplexity, OpenAI, Gemini) keep answers grounded. The
aim: reach a stable Perplexity/Gemini-grade standard while holding hallucination **genuinely** under 10%.

Scope analyzed: retrieval/discovery, RAG/grounding, trust/verification, orchestration/synthesis, and the
API + frontend trust surface — ~40 backend modules and ~27 frontend files.

---

## 0. The headline finding (read this first)

The single most important result of this audit is about **honesty of the number**, not the number itself.

Today's reported hallucination risk is biased **downward** by several independent design choices, so a run
can print "<10%" while the true unsupported-claim rate is materially higher:

1. **Measurement order launders the report.** The 2nd-model verifier rewrites/drops contradicted claims
   (`agents/graph.py:471`) *before* entailment and cosine measure the text (`graph.py:480-486`, risk at
   `:491`). The worst claims are removed from the denominator and never counted.
2. **Unsupported claims are discounted 60%.** `NEI_WEIGHT = 0.4` (`agents/entail.py:70`, formula at
   `:261`). "Not-Enough-Info" means *the cited source does not establish the claim* — that is the core of
   hallucination, yet it counts as less than half a refutation.
3. **Detected problems are not scored.** Cross-source `conflicts` and dead/fabricated citation URLs are
   computed but feed only cosmetic flag strings — never `risk` or `quality_score` (`graph.py:491,528-531`).
4. **Uncited claims are invisible.** Risk's denominator is *cited* sentences only (`entail.py:88`); a
   confident, fabricated, **uncited** sentence costs nothing.
5. **The fallback can't see contradictions.** When the judge covers <50% of claims (or no model), the
   pipeline silently falls back to symmetric cosine, which reports `refuted=0, conflicts=0`
   (`entail.py:228-229`, `:131`). A flaky run looks clean precisely when it is least sure.
6. **The UI presents a degraded run as fully verified.** A cosine-only run still renders the "every claim
   got an entailment verdict" footer and a "none were left unsupported" all-clear
   (`apps/web/components/report/TrustPanel.tsx:55-107,83-86`).

**Why this matters for your "never over 10%" goal.** Real published deep-research tools are nowhere near
10% on adversarial citation tests — independent testing put Gemini 3 Pro at ~76% and Perplexity at ~37%
citation-inaccuracy on one benchmark
([clickittech](https://www.clickittech.com/ai/perplexity-deep-research-vs-openai-deep-research/),
[punku.ai](https://www.punku.ai/blog/comprehensive-analysis-deep-research-implementations)). A genuine
<10% is therefore a *strong* claim that has to be earned two ways at once: **reduce** hallucination at the
source **and** **measure** it honestly. The trap to avoid: tuning the metric down to stay under 10% is
self-certification — it makes the dashboard green while users still get wrong facts. The durable path is
the opposite — make the number honest (it may rise above 10% on some runs first), then drive the *true*
rate down with grounding until the honest number is under 10%.

This is consistent with the trust-scoring work already locked in (uncapped, responsive risk): honest
measurement *extends* that principle. Note one interaction — raising the NEI weight conflicts with the
existing `test_nei_counts_less_than_refuted_toward_hallucination_risk` test, so the fix is a design
decision (see P0-1) rather than a one-line change.

---

## 1. The standard we are measuring against (web research)

| Theme | What the leading systems / literature do | Source |
|---|---|---|
| Grounding architecture | Perplexity is RAG-native, citation-first, real-time retrieval (not parametric); inline sentence-level citations correlate with lower hallucination than paragraph-level | [clickittech](https://www.clickittech.com/ai/perplexity-deep-research-vs-openai-deep-research/), [aiixx](https://aiixx.ai/blog/ai-deep-research-tools-compared-gemini-openai-and-perplexity) |
| Reduce hallucination | RAG cuts hallucination 42–68%; **CRAG** (retrieval evaluation → query rewrite → evidence filtering → explicit refusal on weak context) and **Self-RAG** reach ~0.97 fact-check accuracy; **Chain-of-Verification (CoVe)** drafts, generates verification questions, then revises | [CRAG](https://www.emergentmind.com/topics/corrective-retrieval-augmented-generation-crag), [arXiv 2505.09031](https://arxiv.org/abs/2505.09031), [galileo](https://galileo.ai/blog/mastering-rag-llm-prompting-techniques-for-reducing-hallucinations) |
| Honest faithfulness measurement | **RAGAS** (reference-free faithfulness), **ALCE** citation precision/recall (recall = do cited docs *entail* the sentence; precision = is each citation necessary), **FACTS Grounding** span-level groundedness; report correctness *and* faithfulness, supplement with span-level precision/recall so macro metrics don't mask pseudo-citations | [langcopilot](https://langcopilot.com/posts/2025-09-17-rag-evaluation-101-from-recall-k-to-answer-faithfulness), [deepchecks](https://deepchecks.com/rag-evaluation-metrics-answer-relevancy-faithfulness-accuracy/), [arXiv 2507.18910](https://arxiv.org/pdf/2507.18910) |
| Retrieval stack | 2026 self-hosted default is **BGE-M3** (dense+sparse+multi-vector, 100+ languages, MIT) + **BGE-reranker-v2**; leaders Qwen3-Embedding-8B (MTEB 70.6), Cohere embed-v4, OpenAI text-3-large; small English-only encoders are well below this ceiling | [ailog](https://app.ailog.fr/en/blog/guides/choosing-embedding-models), [FlagEmbedding](https://github.com/FlagOpen/FlagEmbedding) |

**Read:** ATHENA already does the *hard, differentiating* part — entailment NLI, conflict detection,
URL-liveness, span citations, a coverage ledger, mid-loop reading. The gap to the standard is (a) honest
measurement, (b) write-time grounding (CRAG/Self-RAG/CoVe), and (c) a stronger retrieval stack — plus
making the trust visible and the run reliable.

---

## 2. What is already strong (do not break)

- Entailment NLI judge with non-claim filtering, balanced prompt, claim-relevant `_focus` windows, and an
  uncapped/responsive risk formula locked by tests. Cross-source conflict flagging.
- Real cross-encoder reranking; RRF merge; mid-loop reading (read→reflect); coverage ledger driving
  drill/expand/stop; multi-hop citation chasing; section-by-section synthesis with globally consistent
  `[n]` indices (citation index alignment was verified correct).
- Careful SSRF/DNS-rebind defenses in `fetch.py`; model ladder for cost; clickable citations with real
  supporting passages (`select_span`).

---

## 3. Prioritized roadmap

Priority = impact on (research quality × honest <10% hallucination × user-visible trust). Effort: S ≤ ~½ day,
M ≈ 1–3 days, L ≈ multi-day/infra.

### P0 — ULTRA-HIGH (decides whether "<10%" is real and trusted)

**P0-1 — Make the hallucination number honest.** Effort: M.
- Score entailment/cosine on the **pre-verifier** markdown, and count every verifier drop/correction as a
  hallucination event (`graph.py:471` vs `:480-486`).
- Surface the **undiscounted** `(refuted + nei)/total` as the headline unsupported rate; if a softened
  blend is kept for UX, show both (`entail.py:261`). Reconsider `NEI_WEIGHT` (`entail.py:70`) — this is the
  test-interaction noted in §0.
- Fold `conflicts` and dead-citation fraction into `risk`/`quality_score` (`graph.py:528-531`,
  `quality.py:17`).
- Bring **uncited** factual sentences into the denominator (treat as NEI/unsupported) (`entail.py:88`).
- *Standard:* ALCE/RAGAS faithfulness measure support honestly and reference-free.

**P0-2 — Enforce claim-level grounding at write time (the biggest reduce-at-source lever).** Effort: M.
- Today the synthesizer *asks* for citations but nothing forces them (`synthesizer.py:9-23,286-307`); all
  grounding is post-hoc/advisory. Add a gate after `synthesize_sections`: every factual body sentence must
  carry a valid **in-range** `[n]`, else it is hedged or dropped before persist (reuse `guard._sentences`).
- Move `strip_invalid_citations` to run **before** verify/factcheck/entail so fabricated markers are
  counted as hallucinations, not silently dropped (`graph.py:475` → before `:471`).
- *Standard:* Self-RAG / CRAG enforce grounding (and explicit refusal on weak context) at generation time;
  this is what separates "we score hallucination" from "we prevent it."

**P0-3 — NLI as the real support test + an honest fallback.** Effort: M.
- `guard.factcheck` grounds on cosine ≥ 0.55 (`guard.py:47`), which passes paraphrased-but-false claims.
  Use cosine only as a candidate pre-filter; let entailment be the support decision. When entailment is
  unavailable/low-coverage, **do not** claim <10% — widen the band, retry once, or label reduced assurance
  (`entail.py:228-229`).
- *Standard:* cosine measures topical similarity, not entailment; faithfulness must test support.

**P0-4 — Stop the two trust-credibility cliffs in the product.** Effort: S–M.
- Don't emit `done` when `persist_report` failed — emit `failed`/`report_ready:false`; have the UI retry
  `getRun` and 404 empty exports (`graph.py:551-564`, `page.tsx:45-49`, `runs.py:144-158`). Today a
  finish-line DB blip shows a confident "Done" over a blank report.
- Disclose degraded (cosine-only) runs and gate the "none left unsupported" all-clear on
  `engine==="entailment" && total>0` (`TrustPanel.tsx:55-107,83-86`).

### P1 — HIGH (raises the quality ceiling; closes claim-starvation)

**P1-1 — Upgrade the retrieval stack.** Effort: M. Move `bge-small-en-v1.5` (384-dim, English-only,
`embed.py:10`) → **BGE-M3** + **BGE-reranker-v2**. Widen the rerank candidate pool beyond top-48
(`rag.py:99-100`) and rank **all** chunks, not the first 8 (`rag.py:81`). Biggest single retrieval-quality
and multilingual lever.

**P1-2 — Align the grounding checker with the evidence actually shown.** Effort: S. `factcheck` re-chunks
only the first 6000 chars of raw sources (`guard.py:26`); verify against the exact evidence chunks sent to
the synthesizer instead, eliminating claim-starvation false flags.

**P1-3 — Rerank/select on fetched full content, not title+snippet.** Effort: S–M. `relevance.py:50` scores
`title+snippet` even after mid-loop reading has the real body; re-score on fetched content before final
selection. Also fall back to fetched `content` (not snippets) when `build_evidence` is empty
(`graph.py:413-416`).

**P1-4 — Reference-free re-verification (CoVe/CRAG corrective step).** Effort: M. Re-check top claims
against a *fresh, neutralized* search, not just the cited source — defeats the "cited-but-wrong" failure
mode. Add verification questions for the highest-risk claims and revise/flag on disagreement.

**P1-5 — Fix the dedup/content key mismatch.** Effort: S. `dedup_near` returns a normalized key that can
diverge from `e["hit"].url` used downstream (`select.py:91-113`), risking sources selected but assembled
with empty/snippet content — a silent grounding hole. Tag content provenance (full vs snippet) and
down-weight snippet-only sources for substantive claims.

**P1-6 — Recency/freshness handling.** Effort: M. No date-range/time filtering anywhere; the only query
reformulation is a hardcoded English authority hint (`graph.py:209`). Add a topic-conditioned recency path
(per-provider date sort/range) for time-sensitive queries.

**P1-7 — Surface the per-claim verdict table + conflicts (already computed).** Effort: M. Persisted
`claims` verdicts and `trust.conflict_items` are dropped at the UI (`graph.py:538-545`, `runs.py:129`);
expose a `/research/{id}/claims` endpoint and a per-claim table linking each claim to its citation passage.
This turns "trust me, counts" into the auditable ledger that beats paragraph-level citations.

**P1-8 — Provider robustness.** Effort: S–M. Timeouts and 429s become `[]` silently
(`search/registry.py:22-34`, `providers.py`), collapsing source diversity. Honor `Retry-After`/backoff,
distinguish timeout from failure, and surface per-provider drop in run metadata.

### P2 — MEDIUM (depth, integrity, eval, modality)

- **P2-1 Section-synthesis retry/escalation.** Per-section write is single-attempt; on truncation a whole
  section becomes a placeholder string (`synthesizer.py:286-307`). Reuse the shrink/escalate loop from
  `synthesize`. Effort: S.
- **P2-2 Prompt-injection hardening.** Defense is delimiter-only; neutralize/escape the `«UNTRUSTED»`
  tokens in scraped text and prefer a structured evidence channel (`synthesizer.py:114-118`,
  `graphmem.py`, `memory.py`). Effort: M.
- **P2-3 Grounding gates the score.** Make `quality_score` apply a multiplicative penalty/cap when
  `refuted>0` or dead links exist, instead of a flat additive 30 (`quality.py:11-19`). Effort: S.
- **P2-4 Validator authority inflation.** `host.startswith("docs.")`/`/docs` grants a tier
  (`validator.py:54`); require a registered-domain allowlist so `docs.spam-blog.com` isn't "authoritative".
  Effort: S.
- **P2-5 SSE resume + reconnect + per-run token.** Emit SSE `id:`/honor `Last-Event-ID`
  (`events.py:55-76`, `sse.ts`), real reconnect on CLOSED, and a per-run stream capability rather than one
  global token (`runs.py:99-110`, `auth.py`). Effort: M.
- **P2-6 PDF/table-aware extraction.** Extraction is text-only; benchmark numbers live in tables
  (`fetch.py`). Add marker-pdf/LlamaParse-class layout parsing. Effort: M.
- **P2-7 Eval at scale.** Add RAGAS faithfulness + ALCE citation precision/recall + reference-free metrics
  to the harness; track run-over-run (`eval/`). Effort: M. This is how you *prove* the <10% over time.
- **P2-8 Honest corroboration / hop trust gate.** `consensus` counts near-duplicate/syndicated sources as
  independent (`guard.py:55`); cluster by domain/content before counting. Gate unvalidated hop pages behind
  a trust floor (`hop.py:151`). Effort: S–M.

### P3 — LOW (polish, correctness, robustness)

- Charset-aware HTML decode (`fetch.py:148`); absolute score floor under `min_keep` so a wholly off-topic
  batch isn't force-fed 5 irrelevant sources (`relevance.py:58,64`); soft-404/parked detection in urlhealth
  (`urlhealth.py:32`); render unknown `[n]` as "unverified citation" and disable dead-link anchors
  (`ReportView.tsx:11`, `SourceList.tsx:34`); key-test without burning provider tokens (`app.py:121`);
  include embedding model+version in cache keys to avoid mixed-space vectors after an upgrade
  (`cache.py:18`); HTML-parser link extraction in multi-hop instead of regex (`hop.py:26`); share
  claim-filtering between verifier and entail (`verifier.py:29`).

---

## 4. Suggested sequencing

1. **Trust integrity sprint (P0-1…P0-4).** Honest measurement + write-time grounding + NLI support test +
   the two product cliffs. After this, the number means something and the UI never overstates it.
2. **Grounding-quality sprint (P1-1…P1-5).** Retrieval upgrade + checker alignment + content reranking +
   reference-free re-verification + dedup fix. This drives the *true* rate down under 10%.
3. **Visibility + proof (P1-6…P1-8, P2-5, P2-7).** Recency, per-claim ledger UI, provider robustness, SSE
   resume, and the eval harness that proves <10% holds across models over time.
4. **Depth + modality (P2-1…P2-4, P2-6, P2-8) and P3 polish** as capacity allows.

**The moat to protect:** win on *verifiable, auditable* trust. Every P0/P1 item either makes the trust
honest, reduces hallucination at the source, or makes the grounding visible and clickable — which is the
one axis where a focused engine can beat the big players' compute.

---

*Method: file-by-file static audit of `services/api` and `apps/web` (5 subsystem passes) cross-referenced
with current literature on RAG faithfulness, CRAG/Self-RAG/CoVe, and the 2026 retrieval stack. All
`file:line` references point to current code; web sources are linked inline above.*
