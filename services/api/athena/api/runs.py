import asyncio, hmac, json, uuid
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from .events import bus
from .keys import get_key
from .auth import require_auth
from ..config import settings
from ..db import execute, fetch
from ..agents.graph import run_research
from ..report.export import to_markdown_bytes, to_pdf_bytes
from ..search.providers import DuckDuckGoProvider, SearxngProvider, TavilyProvider, SerperProvider

# sensitive routes require the bearer token (when ATHENA_API_TOKEN is set)
router = APIRouter(prefix="/api", dependencies=[Depends(require_auth)])
# SSE stream can't carry an Authorization header from the browser's EventSource. When a token is
# configured it must be passed as ?token=...; the run-id UUID alone is NOT sufficient to read a
# stream once auth is enabled. On localhost (no token configured) the stream stays open.
public_router = APIRouter(prefix="/api")

class LLMSpec(BaseModel):
    provider: str; model: str; api_key: str | None = None
class SearchSpec(BaseModel):
    providers: list[str]; mode: str = "broadcast"; keys: dict[str, str] = {}
class ResearchReq(BaseModel):
    topic: str; rounds: int = 2; llm: LLMSpec; search: SearchSpec; deep: bool = False
    llm_fast: LLMSpec | None = None   # optional fast model for orchestration (plan/refine/reflect)
    report_type: str = "standard"     # standard | literature-review | comparison | how-to | market-scan
    verifier: LLMSpec | None = None   # optional 2nd model that checks/corrects cited claims
    patient: bool = False             # allow slow runs up to ~45 min instead of the 15-min cap
    plan: list[str] | None = None     # user-edited sub-questions; seeds round 1 instead of auto-decompose

class PlanReq(BaseModel):
    topic: str; llm: LLMSpec; llm_fast: LLMSpec | None = None

@router.post("/plan")
async def make_plan(req: PlanReq):
    from ..agents.planner import decompose, extract_entities
    spec = req.llm_fast or req.llm
    if not spec.api_key:
        spec.api_key = await get_key(spec.provider)
    llm = spec.model_dump()
    return {"sub_questions": await decompose(req.topic, n=4, llm=llm),
            "entities": await extract_entities(req.topic, llm)}

def _redacted_params(req: "ResearchReq") -> dict:
    """Strip plaintext provider API keys before persisting the request to research_runs.params.
    The live run still receives the real keys (from req.*.model_dump()); only the stored copy is
    redacted so decrypted vault keys never land in the DB / backups in cleartext."""
    p = req.model_dump()
    for spec in ("llm", "llm_fast", "verifier"):
        if isinstance(p.get(spec), dict):
            p[spec].pop("api_key", None)
    if isinstance(p.get("search"), dict):
        p["search"]["keys"] = {}
    return p

async def create_run(topic: str, rounds: int, params: dict) -> str:
    # generate the id up front + ON CONFLICT DO NOTHING so the db-layer one-shot retry can't insert a
    # duplicate row (and spawn a second token-spending task) when a post-commit blip triggers a retry.
    # NOTE: this guards the DB-retry path only; two distinct HTTP requests still create two runs — the
    # frontend Start button carries a submit guard to prevent accidental double-submits.
    rid = str(uuid.uuid4())
    await execute("insert into research_runs(id,topic,rounds_total,params,status) "
                  "values($1,$2,$3,$4,'running') on conflict (id) do nothing",
                  rid, topic, rounds, json.dumps(params))
    return rid

def build_providers(spec: SearchSpec) -> list:
    reg = {"ddg": lambda: DuckDuckGoProvider(), "searxng": lambda: SearxngProvider(),
           "tavily": lambda: TavilyProvider(spec.keys.get("tavily","")),
           "serper": lambda: SerperProvider(spec.keys.get("serper",""))}
    return [reg[p]() for p in spec.providers if p in reg]

@router.post("/research")
async def start_research(req: ResearchReq):
    if not req.llm.api_key:
        req.llm.api_key = await get_key(req.llm.provider)
    if req.llm_fast and not req.llm_fast.api_key:
        req.llm_fast.api_key = await get_key(req.llm_fast.provider)
    if req.verifier and not req.verifier.api_key:
        req.verifier.api_key = await get_key(req.verifier.provider)
    for name in req.search.providers:
        if name in ("tavily", "serper") and name not in req.search.keys:
            k = await get_key(name)
            if k:
                req.search.keys[name] = k
    run_id = await create_run(req.topic, req.rounds, _redacted_params(req))
    providers = build_providers(req.search)
    from .. import runner
    task = asyncio.create_task(run_research(run_id, req.topic, req.rounds,
        req.llm.model_dump(), providers, req.search.mode, req.deep,
        req.llm_fast.model_dump() if req.llm_fast else None, req.report_type,
        req.verifier.model_dump() if req.verifier else None, req.patient, req.plan))
    runner.register(run_id, task)   # strong ref (no GC) + cancellable
    return {"run_id": run_id}

@public_router.get("/research/{run_id}/stream")
async def stream(run_id: str, request: Request, token: str | None = None,
                 lastEventId: str | None = None):
    # EventSource can't send an Authorization header, so the token rides as ?token=... . Enforce it
    # (constant-time) whenever one is configured, so a run_id alone can't read another run's stream.
    expected = settings.athena_api_token
    if expected and not (token and hmac.compare_digest(token, expected)):
        raise HTTPException(status_code=401, detail="Missing or invalid stream token.")

    # Resume support (P2-5): browsers auto-send `Last-Event-ID` on their own reconnect; our manual JS
    # reconnect passes `?lastEventId=`. Honor either so a reconnect resumes instead of replaying the
    # whole backlog (which doubles sources/counters). Non-int -> start from the beginning.
    raw = request.headers.get("Last-Event-ID") or lastEventId
    try:
        last_id = int(raw) if raw is not None else None
    except (TypeError, ValueError):
        last_id = None

    async def gen():
        async for seq, ev in bus.subscribe_seq(run_id, last_event_id=last_id):
            yield {"id": str(seq), "event": ev["type"], "data": json.dumps(ev["data"])}
    return EventSourceResponse(gen())

@router.post("/research/{run_id}/cancel")
async def cancel(run_id: str):
    from .. import runner
    bus.cancel(run_id)
    runner.cancel_task(run_id)   # actually stop the running task, not just set a flag
    # guard on status='running' so a cancel can't overwrite an already-finalized (done/failed) run
    await execute("update research_runs set status='cancelled', completed_at=now() "
                  "where id=$1 and status='running'", run_id)
    return {"ok": True}

@router.get("/research/{run_id}")
async def get_run(run_id: str):
    # enumerate columns (not select *) so a future column can't leak into the API response by accident
    run = await fetch("select id, topic, status, rounds_total, quality_score, created_at, completed_at "
                      "from research_runs where id=$1", run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    rep = await fetch("select markdown, quality_breakdown, citations, flagged, trust from reports "
                      "where run_id=$1 order by created_at desc limit 1", run_id)
    srcs = await fetch("select url,title,source_type,round,validated,trust_score from sources where run_id=$1", run_id)
    r0 = rep[0] if rep else None
    def _j(v, default):
        if v is None: return default
        return json.loads(v) if isinstance(v, str) else v
    return {"run": dict(run[0]) if run else None,
            "report": r0["markdown"] if r0 else None,
            "quality_breakdown": _j(r0["quality_breakdown"], None) if r0 else None,
            "citations": _j(r0["citations"], []) if r0 else [],
            "flagged": _j(r0["flagged"], []) if r0 else [],
            "trust": _j(r0["trust"], {}) if r0 else {},
            "sources": [dict(s) for s in srcs]}

@router.get("/research/{run_id}/claims")
async def get_claims(run_id: str):
    """Per-claim entailment verdicts (the audit trail) persisted by persist_claims (P1-7). Conflicts and
    low-confidence claims surface first. 404 only when the run is unknown; an empty list is a valid 200."""
    run = await fetch("select id from research_runs where id=$1", run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    rows = await fetch(
        "select text, verdict, confidence, conflict from claims "
        "where run_id=$1 order by conflict desc, confidence asc nulls last", run_id)
    return {"claims": [
        {"text": r["text"], "verdict": r["verdict"],
         "confidence": float(r["confidence"]) if r["confidence"] is not None else None,
         "conflict": bool(r["conflict"])}
        for r in rows]}

@router.get("/research/{run_id}/report.md")
async def report_md(run_id: str):
    rep = await fetch("select markdown from reports where run_id=$1 order by created_at desc limit 1", run_id)
    if not rep or not rep[0]["markdown"]:
        raise HTTPException(status_code=404, detail="No report for this run")   # don't save a placeholder as a "report" (P3)
    md = rep[0]["markdown"]
    return Response(to_markdown_bytes(md), media_type="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="report-{run_id}.md"'})

@router.get("/research/{run_id}/report.pdf")
async def report_pdf(run_id: str):
    rep = await fetch("select markdown from reports where run_id=$1 order by created_at desc limit 1", run_id)
    if not rep or not rep[0]["markdown"]:
        raise HTTPException(status_code=404, detail="No report for this run")
    md = rep[0]["markdown"]
    # offload the synchronous CPU/IO-heavy PDF render to a worker thread so it can't block the loop
    pdf = await asyncio.to_thread(to_pdf_bytes, md)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="report-{run_id}.pdf"'})
