import asyncio

from ..api.events import bus
from ..search.base import SearchHit
from ..search.registry import multi_search
from ..search.merge import rrf_merge
from ..search.relevance import filter_by_relevance
from ..search.specialist import arxiv_search, github_search
from ..fetch import fetch_many
from ..rag import build_evidence, select_span
from .select import select_sources, assemble_content, dedup_near
from .planner import decompose, refine, extract_entities, expand_facets
from .controller import reflect
from .synthesizer import synthesize_sections, strip_invalid_citations
from .verifier import verify_report
from .entail import entail_report
from .urlhealth import check_urls, summarize as urlhealth_summary
from .coverage import compute_coverage, weakest_questions, coverage_note
from .persist import persist_sources, persist_report, persist_claims
from . import hop
from . import graphmem
from ..memory import recall, remember
from .validator import score_source, is_validated
from .guard import factcheck
from .quality import quality_score
from ..gateway import ladder
from ..log import get_logger

log = get_logger(__name__)
READ_PER_ROUND = 10  # mid-loop reading budget: fetch the top-N new sources each round (agentic read->reflect).
                     # Raised 6->10 so each round genuinely browses+validates real content (less "gimmick round").
SELECT_N = 24        # sources fed to synthesis — combine more of the pool into one report (was 20)
MAX_SUBAGENTS = 4    # metered concurrency: at most N sub-question research workers run at once
MIN_READ_PER_SUBQ = 2  # breadth-first reading: guarantee >=N reads for EACH sub-question so no cell starves
# research-quality gates (see docs/ARCHITECTURE.md for the research-loop design)
SPECIALIST_REL_FLOOR = 0.45   # drop off-topic arXiv/GitHub seeds below this (kills pool pollution)
VALIDATE_REL_FLOOR = 0.4      # a source counts as "validated" if it's authoritative AND not clearly
                              # off-topic. Decoupled from the strict 0.6 relevance floor that zeroed the
                              # validation metric — authority + on-topic-ish is the real trust signal.
MIN_ROUNDS = 2                # deep mode may not "stop" before this many rounds on a multi-part query
MAX_FACETS = 6                # adaptive-planning cap: facets grow (append-only) up to this, never beyond
POOL_CAP = 28                 # bound the discovered pool to the best sources (was 20). Wider pool +
                              # authority weighting => more sources combined without diluting on junk.


def _cap_pool(all_hits: dict, cap: int = POOL_CAP) -> dict:
    """Keep only the strongest `cap` sources: validated first, then by trust-weighted relevance. This
    undilutes the validation ratio (validated/discovered) without losing any authoritative source."""
    if len(all_hits) <= cap:
        return all_hits
    ranked = sorted(all_hits.items(),
                    key=lambda kv: (kv[1].get("validated", False),
                                    kv[1].get("trust", 0.0) * 0.6 + kv[1].get("relevance", 0.0) * 0.4),
                    reverse=True)
    return dict(ranked[:cap])


def _sufficient(rnd: int, all_hits: dict, questions: list, new_this_round: int,
                coverage: dict | None = None) -> bool:
    """Honor a controller 'stop' only after a genuine PLATEAU — a round that added no new sources —
    once past MIN_ROUNDS. With adaptive planning, 'all facets covered' is a reason to WIDEN the plan,
    not to quit, so a deep run uses its full round budget unless there is truly nothing new to find
    (which still keeps it bounded by the caller's <=5-round cap)."""
    if rnd < MIN_ROUNDS:
        return False
    return new_this_round == 0                  # plateau: nothing new this round -> truly done


def _friendly_error(e: Exception) -> str:
    from ..gateway.llm import redact_keys
    low = str(e).lower()
    if "invalid api key" in low or "invalid_api_key" in low or "401" in low or "unauthorized" in low:
        return "Invalid API key for this provider — check it in API Keys."
    if "rate limit" in low or "rate_limit" in low or "429" in low:
        return "Rate limited by the model provider. Wait a moment and retry."
    if "not found" in low and "model" in low:
        return "That model isn't available for this provider — pick another model."
    if "timeout" in low or "timed out" in low:
        return "The model took too long to respond (timed out). Try again."
    return redact_keys(f"Research failed: {str(e)[:180]}")


async def _heartbeat(run_id: str, interval: float = 20.0):
    """Emit a periodic keepalive so the browser's SSE inactivity watchdog doesn't kill a healthy run
    during a long silent phase — e.g. a reasoning model 'thinking' for minutes before it streams the
    report. Cancelled when the run finishes."""
    try:
        while True:
            await asyncio.sleep(interval)
            try:
                await bus.publish(run_id, {"type": "heartbeat", "data": {}})
            except Exception:
                pass
    except asyncio.CancelledError:
        pass


async def run_research(run_id: str, topic: str, rounds: int, llm: dict,
                       providers: list, mode: str, deep: bool = False,
                       llm_fast: dict | None = None, report_type: str = "standard",
                       verifier: dict | None = None, patient: bool = False,
                       plan: list[str] | None = None) -> str:
    from .. import runner
    rounds = max(1, min(int(rounds or 1), 5))   # budget cap: never more than 5 rounds
    time_budget = 2700 if patient else 900      # patient mode lets slow reasoning models finish (~45 min)
    sem = runner.semaphore()
    if sem.locked():                            # at the concurrency cap -> tell the client it's queued
        try:
            await bus.publish(run_id, {"type": "queued", "data": {}})
        except Exception:
            pass
    async with sem:                             # bound concurrent runs; queue wait doesn't count toward budget
        hb = asyncio.create_task(_heartbeat(run_id))   # keep the SSE alive through long silent phases
        try:
            return await asyncio.wait_for(
                _run_research_inner(run_id, topic, rounds, llm, providers, mode, deep, llm_fast,
                                    report_type, verifier, plan),
                timeout=time_budget)
        except asyncio.TimeoutError:
            try:
                await bus.publish(run_id, {"type": "failed", "data": {
                    "message": "Research exceeded the time budget and was stopped."}})
            except Exception:
                pass
            try:
                from ..db import execute
                await execute("update research_runs set status='failed', completed_at=now() where id=$1", run_id)
            except Exception:
                pass
            return ""
        except asyncio.CancelledError:          # user cancel -> stop cleanly, mark cancelled
            try:
                await bus.publish(run_id, {"type": "cancelled", "data": {}})
            except Exception:
                pass
            try:
                from ..db import execute
                await execute("update research_runs set status='cancelled', completed_at=now() where id=$1", run_id)
            except Exception:
                pass
            return ""
        except Exception as e:
            msg = _friendly_error(e)
            try:
                await bus.publish(run_id, {"type": "failed", "data": {"message": msg}})
            except Exception:
                pass
            try:
                from ..db import execute
                await execute("update research_runs set status='failed', completed_at=now() where id=$1", run_id)
            except Exception:
                pass
            return ""
        finally:
            hb.cancel()                         # stop the keepalive once the run settles


async def _seed_specialists(run_id: str, topic: str, all_hits: dict):
    # run both specialist sources in parallel and isolate their failures: a GitHub rate-limit
    # must NOT discard already-fetched arXiv papers (and vice versa).
    ax, gh = await asyncio.gather(arxiv_search(topic, k=5), github_search(topic, k=4),
                                  return_exceptions=True)
    specials = []
    for name, res in (("arxiv", ax), ("github", gh)):
        if isinstance(res, Exception):
            log.warning("specialist %s seeding failed: %s", name, res)
        elif res:
            specials += res
    if not specials:
        return
    info, hits = {}, []
    from ..fetch import _is_safe_url
    for sp in specials:
        if not _is_safe_url(sp["url"]):
            continue
        h = SearchHit(url=sp["url"], title=sp["title"], snippet=sp.get("snippet", ""),
                      rank=0, provider="specialist")
        hits.append(h)
        info[sp["url"]] = (sp["content"], sp["source_type"])
    # relevance-filter specialist results too — arXiv/GitHub APIs sometimes return off-topic
    # papers (e.g. unrelated physics) for a multi-topic query; don't trust them blindly.
    hits = await asyncio.to_thread(filter_by_relevance, topic, hits)
    for h in hits:
        key = h.url.rstrip("/").lower()
        if key in all_hits:
            continue
        if getattr(h, "relevance", 0.0) < SPECIALIST_REL_FLOOR:
            continue   # off-topic specialist seed (e.g. unrelated arXiv paper) — don't pollute the pool
        content, stype = info[h.url]
        trust = score_source(h.url, h.title)
        valid = is_validated(h.url, h.title) and h.relevance >= VALIDATE_REL_FLOOR  # authoritative AND on-topic
        all_hits[key] = {"hit": h, "round": 1, "source_type": stype, "trust": trust,
                         "validated": valid, "relevance": h.relevance, "content": content,
                         "subq": ""}   # topic-level seed — not attributed to a specific sub-question
        await bus.publish(run_id, {"type": "source", "data": {
            "url": h.url, "title": h.title, "provider": "specialist", "source_type": stype,
            "round": 1, "trust": trust, "validated": valid, "relevance": h.relevance,
            "providers": ["specialist"], "subquestion": topic}})


async def _fanout_search(question: str, entities: list, providers: list, mode: str, k: int):
    """Search a sub-question across providers AND a couple of entity-grounded reformulations, then
    RRF-merge — broadens retrieval toward the named subjects instead of one fixed phrasing."""
    queries = [question]
    for ent in (entities or [])[:2]:
        if ent and ent.lower() not in question.lower():
            queries.append(f"{ent} {question}")
    # authority-intent variant: surfaces official docs / specs / standards (the domains that validate)
    queries.append(f"{question} official documentation OR specification")
    queries = queries[:4]   # bound fan-out cost
    results = await asyncio.gather(*[multi_search(q, providers, mode=mode, k=k) for q in queries])
    lists = [r for r in results if r]
    if len(lists) <= 1:
        return lists[0] if lists else []
    return rrf_merge(lists, k=60)


async def _subagent(topic: str, q: str, entities: list, providers: list, mode: str, k: int,
                    sem: asyncio.Semaphore):
    """One breadth-first research worker for a single sub-question: fan-out search + relevance filter,
    bounded by ``sem`` (metered concurrency). Returns ``(question, relevance-filtered hits)``. Isolated:
    one sub-question's failure returns [] and never sinks the others."""
    async with sem:
        try:
            hits = await _fanout_search(q, entities, providers, mode, k)
            hits = await asyncio.to_thread(filter_by_relevance, topic, hits)
            return q, hits
        except Exception as e:
            log.warning("sub-agent for %r failed: %s", q[:60], e)
            return q, []


def _round_digest(all_hits: dict, top_n: int = 8) -> str:
    """Compact digest of the strongest current hits. Uses fetched page CONTENT when available
    (mid-loop reading) so refine/reflect reason over what the sources actually say, not just titles."""
    entries = sorted(all_hits.values(), key=lambda e: e.get("relevance", 0.0), reverse=True)[:top_n]
    out = []
    for e in entries:
        body = (e.get("content") or e["hit"].snippet or "")[:300]
        out.append(f"{e['hit'].title} — {body}")
    return "\n".join(out)


async def _read_top(run_id: str, all_hits: dict, rnd: int) -> None:
    """Fetch + extract this round's unread sources so reflection/refinement see real content. Reads are
    BREADTH-FIRST: guarantee up to MIN_READ_PER_SUBQ reads for EACH sub-question (no starved cell)
    before filling the rest by global relevance. Stored on each entry's 'content'; final selection
    reuses it (no re-fetch). Never fatal."""
    unread = [e for e in all_hits.values() if not e.get("content")]
    if not unread:
        return
    by_rel = sorted(unread, key=lambda e: e.get("relevance", 0.0), reverse=True)
    by_subq: dict[str, list] = {}
    for e in by_rel:
        by_subq.setdefault(e.get("subq", ""), []).append(e)   # each list stays relevance-sorted
    picked, seen = [], set()
    # (a) round-robin: every sub-question's 1st pick before any 2nd, up to MIN_READ_PER_SUBQ each
    for depth in range(MIN_READ_PER_SUBQ):
        for items in by_subq.values():
            if depth < len(items) and id(items[depth]) not in seen:
                picked.append(items[depth]); seen.add(id(items[depth]))
    # (b) fill the remaining budget by global relevance
    for e in by_rel:
        if len(picked) >= READ_PER_ROUND:
            break
        if id(e) not in seen:
            picked.append(e); seen.add(id(e))
    to_read = picked[:READ_PER_ROUND]
    try:
        docs = await fetch_many([e["hit"].url for e in to_read], limit=READ_PER_ROUND)
    except Exception as ex:
        log.warning("round %d: mid-loop fetch failed: %s", rnd, ex)
        docs = {}
    got = skipped = 0
    for e in to_read:
        txt = docs.get(e["hit"].url)
        if txt:
            e["content"] = txt
            got += 1
        else:
            skipped += 1
    if skipped:
        log.info("round %d: %d/%d sources unreadable (skipped)", rnd, skipped, len(to_read))
    if got or skipped:
        await bus.publish(run_id, {"type": "reading", "data": {"round": rnd, "count": got, "skipped": skipped}})


async def _run_research_inner(run_id: str, topic: str, rounds: int, llm: dict,
                              providers: list, mode: str, deep: bool = False,
                              llm_fast: dict | None = None, report_type: str = "standard",
                              verifier: dict | None = None, plan: list[str] | None = None) -> str:
    # model ladder: route the many cheap orchestration calls (plan/refine/reflect/triage/entail) to the
    # fast tier and reserve the strong model for synthesis. `fast` == llm_fast or llm by the ladder rules.
    fast = ladder.for_role("plan", llm, llm_fast, verifier)
    all_hits: dict[str, dict] = {}
    findings_text = ""
    cov: dict = {}   # coverage ledger (sub-question x entity); last round's value rides on the report
    # facets = the STABLE sub-questions the coverage ledger tracks; kept fixed across rounds so a source
    # found in round 1 still maps to the same cell in round 5. (refine used to rewrite the questions every
    # round, which drifted coverage attribution to 0% and made the run never satisfy its stop condition.)
    facets = [q for q in (plan or []) if q and q.strip()] or await decompose(topic, n=4, llm=fast)
    search_set = list(facets)   # round 1 researches every facet; later rounds drill the under-covered ones

    # seed real, extractable specialist sources (arXiv abstracts + GitHub READMEs)
    await _seed_specialists(run_id, topic, all_hits)
    entities = await extract_entities(topic, fast)

    for rnd in range(1, rounds + 1):
        if bus.is_cancelled(run_id):
            await bus.publish(run_id, {"type": "cancelled", "data": {}}); return ""
        await bus.publish(run_id, {"type": "round_start", "data": {"round": rnd, "questions": search_set}})

        new_this_round = 0                          # for sufficiency / plateau detection (R3)
        # breadth-first orchestration: one metered sub-agent per facet under research this round,
        # researched concurrently (capped at MAX_SUBAGENTS) so every facet is explored in parallel.
        sem = asyncio.Semaphore(MAX_SUBAGENTS)
        subagent_results = await asyncio.gather(
            *[_subagent(topic, q, entities, providers, mode, 8, sem) for q in search_set])
        from ..fetch import _is_safe_url
        for q, hits in subagent_results:
            for hit in hits:
                if not _is_safe_url(hit.url):
                    continue
                key = hit.url.rstrip("/").lower()
                if key not in all_hits:
                    new_this_round += 1
                    stype = _classify(hit.url)
                    trust = score_source(hit.url, hit.title)
                    valid = is_validated(hit.url, hit.title) and getattr(hit, "relevance", 0.0) >= VALIDATE_REL_FLOOR
                    all_hits[key] = {"hit": hit, "round": rnd, "source_type": stype,
                                     "trust": trust, "validated": valid,
                                     "relevance": getattr(hit, "relevance", 0.0),
                                     "subq": q}   # attribute to its sub-question for the coverage ledger
                    await bus.publish(run_id, {"type": "source", "data": {
                        "url": hit.url, "title": hit.title, "provider": hit.provider,
                        "source_type": stype, "round": rnd, "trust": trust, "validated": valid,
                        "relevance": getattr(hit, "relevance", 0.0),
                        "providers": hit.providers, "subquestion": q}})
        await bus.publish(run_id, {"type": "progress", "data": {"round": rnd, "discovered": len(all_hits)}})

        validated_count = sum(1 for e in all_hits.values() if e["validated"])
        await bus.publish(run_id, {"type": "validated", "data": {"count": validated_count}})
        try:
            await persist_sources(run_id, all_hits)
        except Exception as e:
            log.warning("round %d: persist_sources failed (continuing): %s", rnd, e)
        await _read_top(run_id, all_hits, rnd)     # mid-loop reading: fetch top sources so reflect sees real content
        # multi-hop: follow the strongest read sources' outbound links to primary sources (one bounded
        # hop, SSRF-guarded). The fetched primaries join the pool/coverage. Best-effort, no LLM cost.
        try:
            new_this_round += await hop.chase(run_id, topic, all_hits, rnd)   # count primaries toward progress
        except Exception as e:
            log.warning("round %d: multi-hop chase failed (continuing): %s", rnd, e)
        findings_text = _round_digest(all_hits)    # title + fetched content, rebuilt from best current hits

        # coverage ledger: score how well each STABLE facet / entity is covered by validated, on-topic
        # evidence, stream it, and pick the under-covered facets to DRILL next round.
        cov = compute_coverage(all_hits, facets, entities)
        await bus.publish(run_id, {"type": "coverage", "data": cov})
        weak = weakest_questions(cov, n=len(facets))   # every under-covered facet is a drill candidate
        if rnd < rounds:
            decision = None
            if deep:
                # autonomous controller: reflect and decide stop-early / drill-down / continue
                validated_now = sum(1 for e in all_hits.values() if e["validated"])
                note = coverage_note(cov)
                findings_for_reflect = findings_text + (f"\n\nCOVERAGE GAPS: {note}" if note else "")
                decision = await reflect(topic, findings_for_reflect, facets, rnd, rounds, fast,
                                         validated=validated_now, target=max(4, len(facets)))
                await bus.publish(run_id, {"type": "reflect", "data": {
                    "round": rnd, "action": decision["action"], "reason": decision["reason"]}})
            # decide next round's work: drill gaps -> else adaptively EXPAND the plan -> else stop/re-sweep
            if weak:
                # under-covered facets remain: drill them — unless the round made no progress (plateau)
                # and the controller is satisfied, in which case they can't be improved -> stop.
                if deep and decision and decision["action"] == "stop" \
                        and _sufficient(rnd, all_hits, facets, new_this_round, cov):
                    break
                search_set = weak
            else:
                # current scope is covered: adaptive planning widens the plan with a NEW facet (append-only,
                # capped) before we consider stopping — Gemini's "plan -> iterate".
                expanded: list[str] = []
                if len(facets) < MAX_FACETS:
                    cand = await expand_facets(topic, facets, findings_text, n=2, llm=fast)
                    seen_f = {x.strip().lower() for x in facets}
                    expanded = [c.strip() for c in cand
                                if c.strip() and c.strip().lower() not in seen_f][:MAX_FACETS - len(facets)]
                if expanded:
                    facets.extend(expanded)
                    await bus.publish(run_id, {"type": "plan_expand", "data": {"round": rnd, "added": expanded}})
                    search_set = expanded       # explore the newly added facets next round
                elif deep and decision and decision["action"] == "stop" \
                        and _sufficient(rnd, all_hits, facets, new_this_round, cov):
                    break                       # covered, nothing to add, controller satisfied -> stop
                else:
                    search_set = list(facets)   # re-sweep; a plateau then ends the loop

    if bus.is_cancelled(run_id):
        await bus.publish(run_id, {"type": "cancelled", "data": {}}); return ""

    # bound the pool to the best sources before scoring/selection (undilute the validation ratio)
    all_hits = _cap_pool(all_hits)
    # smart selection: trust x relevance + type diversity, prefer validated
    selected = select_sources(dedup_near(all_hits), n=SELECT_N, entities=entities)
    fetch_urls = [e["hit"].url for e in selected if not e.get("content")]
    await bus.publish(run_id, {"type": "fetching", "data": {"count": len(fetch_urls)}})
    docs = await fetch_many(fetch_urls, limit=SELECT_N)
    content = assemble_content(selected, docs)   # specialist > extracted > snippet fallback
    content_fetched = len(content)
    meta = {e["hit"].url: {"trust": e.get("trust", 0.5), "source_type": e.get("source_type", "web")}
            for e in selected}
    evidence = await asyncio.to_thread(build_evidence, topic, content, meta, k=32)   # embed+rerank off the loop
    if not evidence:
        evidence = [{"url": e["hit"].url, "text": e["hit"].snippet, "score": e.get("relevance", 0.0)}
                    for e in selected if e["hit"].snippet]

    # cross-run memory: pull continuity context from prior related runs (best-effort, never fatal)
    prior_context = ""
    try:
        prior = await recall(topic, k=3, exclude_run_id=run_id)
        if prior:
            await bus.publish(run_id, {"type": "memory", "data": {"related": [
                {"topic": p["topic"], "similarity": round(float(p["similarity"]), 3)} for p in prior]}})
            prior_context = "\n".join(
                f"- (earlier research on '{p['topic']}'): {(p['summary'] or '')[:500]}" for p in prior)
    except Exception as e:
        log.warning("cross-run memory recall failed: %s", e)
        prior_context = ""
    # GraphRAG: enrich with the 1-hop neighborhood of the topic's entities (opt-in; no-op when off)
    try:
        kg = await graphmem.neighborhood(entities)
        if kg:
            prior_context = (prior_context + "\n\n" + kg).strip()
    except Exception as e:
        log.warning("graphmem neighborhood failed (continuing): %s", e)

    if bus.is_cancelled(run_id):                # don't start the expensive synthesis if cancelled mid-fetch
        await bus.publish(run_id, {"type": "cancelled", "data": {}}); return ""
    await bus.publish(run_id, {"type": "synthesizing", "data": {}})

    # stream the report as it's written + capture token usage (best-effort)
    async def _on_delta(t):
        try:
            await bus.publish(run_id, {"type": "report_delta", "data": {"text": t}})
        except Exception:
            pass

    async def _on_reasoning(t):
        try:
            await bus.publish(run_id, {"type": "reasoning_delta", "data": {"text": t}})
        except Exception:
            pass

    usage_box: dict = {}
    # section-by-section synthesis: outline -> per-section targeted retrieval -> grounded section, with
    # globally-numbered citations. Outline runs on the cheap tier; degrades to single-pass if thin.
    markdown, order, src_texts = await synthesize_sections(
        topic, evidence, llm, plan_llm=ladder.for_role("outline", llm, llm_fast, verifier), facets=facets,
        prior_context=prior_context, report_type=report_type,
        on_delta=_on_delta, on_reasoning=_on_reasoning, on_usage=usage_box.update,
        entities=entities)
    if usage_box:
        await bus.publish(run_id, {"type": "usage", "data": usage_box})

    source_texts_in_order = [src_texts.get(u, "") for u in order]

    # second-model verification: an independent model corrects/flags each cited claim (best-effort)
    verifier_contested: list[str] = []
    if verifier:
        markdown, verifier_contested = await verify_report(markdown, source_texts_in_order, verifier)
        await bus.publish(run_id, {"type": "verify", "data": {"contested": len(verifier_contested)}})

    # R5: drop any fabricated out-of-range citation markers before grounding/persist
    markdown = strip_invalid_citations(markdown, len(order))

    # factcheck runs local embedding inference (CPU-bound); offload so it never freezes the event
    # loop (and starves other concurrent runs sharing this process). This is the deterministic
    # grounding baseline AND the fallback for the entailment layer below.
    g = await asyncio.to_thread(factcheck, markdown, source_texts_in_order)

    # ENTAILMENT (the trust moat): a model judges each cited claim Supported / Refuted / Not-Enough-Info
    # and flags cross-source conflicts. Cosine is symmetric and can't see contradictions; entailment can.
    # Runs on the fast model and degrades to the cosine signal above if unavailable / too thinly covered.
    ent = await entail_report(markdown, source_texts_in_order, fast, factcheck=g)
    await bus.publish(run_id, {"type": "entail", "data": {
        "engine": ent["engine"], "supported": ent["supported"], "refuted": ent["refuted"],
        "nei": ent["nei"], "conflicts": ent["conflicts"]}})
    # entailment risk supersedes the cosine risk only when the model actually judged the claims
    risk = ent["risk"] if ent["engine"] == "entailment" else g["risk"]

    # URL liveness / fabrication detection: probe every cited source URL (SSRF-guarded) and badge
    # dead links instead of citing them blindly — the cheapest trust win nobody else does.
    health = await check_urls(list(order))
    hsum = urlhealth_summary(health)
    if health:
        await bus.publish(run_id, {"type": "urlhealth", "data": {
            "total": hsum["total"], "live": hsum["live"], "dead": hsum["dead"],
            "unreachable": hsum["unreachable"]}})

    validated_count = sum(1 for e in all_hits.values() if e["validated"])
    rels = [e["relevance"] for e in all_hits.values()]
    avg_rel = sum(rels) / len(rels) if rels else 0.0
    qual = quality_score(len(all_hits), validated_count, risk, rounds,
                         avg_relevance=avg_rel, content_fetched=content_fetched)
    await bus.publish(run_id, {"type": "quality", "data": {
        "score": qual["score"], "breakdown": qual["breakdown"], "hallucination_risk": risk,
        "consensus": g.get("consensus")}})

    title_by_url = {e["hit"].url: e["hit"].title for e in selected}
    # span-level citations: surface the most on-topic sentence per source instead of the first 400 chars.
    # select_span reranks with a cross-encoder (CPU-bound); build all citations in a worker thread
    # so the per-citation inference doesn't block the event loop.
    def _build_citations():
        return [{"n": i + 1, "url": u, "title": title_by_url.get(u, u),
                 "excerpt": select_span(topic, src_texts.get(u, "") or "", max_chars=400),
                 "url_status": (health.get(u) or {}).get("status")}
                for i, u in enumerate(order)]
    citations = await asyncio.to_thread(_build_citations)
    # use whichever grounding engine actually ran for the per-claim warnings (entailment supersedes cosine)
    trust_flags = ent["flagged"] if ent["engine"] == "entailment" else (g.get("flagged") or [])
    dead_links = [u for u in hsum["bad"] if (health.get(u) or {}).get("status") == "dead"]
    flagged = (trust_flags[:10] + verifier_contested[:6]
               + [f"⚠ [link dead] {u}" for u in dead_links[:4]]
               + [f"⚠ single-source (uncorroborated): {s}" for s in (g.get("single_source") or [])[:4]])
    breakdown = dict(qual["breakdown"]); breakdown["hallucination_risk"] = risk
    if usage_box.get("total_tokens"):
        breakdown["tokens"] = usage_box["total_tokens"]
    if usage_box.get("cost") is not None:
        breakdown["cost_usd"] = usage_box["cost"]
    # structured trust ledger (the audit trail) persisted on the report + per-claim verdicts to `claims`
    trust = {"engine": ent["engine"], "supported": ent["supported"], "refuted": ent["refuted"],
             "nei": ent["nei"], "conflicts": ent["conflicts"],
             "conflict_items": ent.get("conflict_items", []),
             "consensus": g.get("consensus"), "single_source": len(g.get("single_source") or []),
             "url_health": {"total": hsum["total"], "live": hsum["live"], "dead": hsum["dead"],
                            "unreachable": hsum["unreachable"]},
             "url_status": {u: r.get("status") for u, r in health.items()},
             "coverage": cov}
    if ent.get("verdicts"):
        try:
            await persist_claims(run_id, ent["verdicts"])
        except Exception as e:
            log.warning("persist_claims failed (continuing): %s", e)
    try:
        await persist_report(run_id, markdown, qual["score"], breakdown, citations, flagged, trust)
    except Exception as e:
        # a DB blip at the finish line must NOT discard a fully-synthesized report -> still emit done
        log.error("persist_report failed (report was produced; surfacing it anyway): %s", e)
    try:
        await remember(run_id, topic, markdown)   # store this run for future recall (best-effort)
    except Exception:
        pass
    try:
        await graphmem.extract_and_store(run_id, all_hits, fast)   # GraphRAG triples (opt-in; no-op when off)
    except Exception as e:
        log.warning("graphmem extract_and_store failed (continuing): %s", e)
    await bus.publish(run_id, {"type": "done", "data": {"report_ready": True, "quality": qual["score"]}})
    return markdown


def _classify(url: str) -> str:
    u = url.lower()
    if "github.com" in u: return "github"
    if "arxiv.org" in u or "doi.org" in u or "semanticscholar" in u: return "paper"
    if "docs." in u or "/docs" in u: return "docs"
    if "medium.com" in u or "substack" in u or "blog" in u: return "blog"
    if "news" in u: return "news"
    return "web"
