from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from .runs import router, public_router
from .skills import router as skills_router
from .keys import set_key, get_key, list_keys, delete_key
from .auth import require_auth
from ..gateway.registry import list_providers, list_models, PROVIDERS
from ..db import execute
from ..config import settings
from ..log import get_logger

log = get_logger(__name__)


async def reconcile_stale_runs():
    """Fire-and-forget runs are lost on restart; mark long-stuck 'running' rows failed so the
    UI doesn't show perpetual spinners. Guarded so a down DB never blocks API startup."""
    try:
        await execute("update research_runs set status='failed', completed_at=now() "
                      "where status='running' and created_at < now() - interval '20 minutes'")
    except Exception:
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    prod = settings.athena_env != "dev"
    # Fail loud rather than silently using an ephemeral key that orphans the vault on restart.
    if not settings.athena_secret:
        if prod:
            raise RuntimeError(
                "ATHENA_SECRET must be set when ATHENA_ENV != 'dev' — without it the API-key vault "
                "is encrypted under an ephemeral local key that is lost on restart.")
        log.warning("ATHENA_SECRET is unset — using an ephemeral local key file (dev only). "
                    "Set ATHENA_SECRET before any non-localhost deploy.")
    else:
        # validate it's a usable Fernet key NOW, not on the first vault op (which would 500 at runtime)
        try:
            from cryptography.fernet import Fernet
            Fernet(settings.athena_secret.encode())
        except Exception as e:
            raise RuntimeError(f"ATHENA_SECRET is not a valid Fernet key: {e}")
    # auth: warn on localhost, but make it fatal in prod so an operator can't silently ship open.
    if not settings.athena_api_token:
        if prod:
            raise RuntimeError(
                "ATHENA_API_TOKEN must be set when ATHENA_ENV != 'dev' — otherwise the API is fully "
                "unauthenticated. Set it before exposing the API to a network.")
        log.warning("ATHENA_API_TOKEN is unset — the API is UNAUTHENTICATED. Fine for localhost; "
                    "set it before exposing the API to a network.")
    if prod and "*" in settings.cors_origins_list:
        raise RuntimeError("ATHENA_CORS_ORIGINS must not be '*' when ATHENA_ENV != 'dev'.")
    await reconcile_stale_runs()
    yield
    from ..db import close_pool
    await close_pool()


app = FastAPI(title="ATHENA API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins_list,
                   allow_methods=["*"], allow_headers=["*"])
app.include_router(router)
app.include_router(public_router)
app.include_router(skills_router)   # /api/rerank + /api/verify — engine skills for the ADK agent

@app.get("/api/providers", dependencies=[Depends(require_auth)])
def providers(): return {"providers": list_providers()}

@app.get("/api/providers/{provider}/models", dependencies=[Depends(require_auth)])
async def models(provider: str, x_provider_key: str | None = Header(None, alias="X-Provider-Key")):
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail=f"Unknown provider '{provider}'")
    key = x_provider_key or await get_key(provider)   # key via header, never the URL query string
    return {"models": await list_models(provider, key)}

@app.get("/api/health")
async def health():
    from ..db import fetch
    db_ok = True
    try:
        await fetch("select 1")
    except Exception:
        db_ok = False
    return {"ok": True, "db": db_ok}

class KeyBody(BaseModel):
    api_key: str

@app.get("/api/keys", dependencies=[Depends(require_auth)])
async def get_keys():
    return {"keys": await list_keys()}

@app.put("/api/keys/{provider}", dependencies=[Depends(require_auth)])
async def put_key(provider: str, body: KeyBody):
    await set_key(provider, body.api_key)
    return {"ok": True, "provider": provider}

@app.delete("/api/keys/{provider}", dependencies=[Depends(require_auth)])
async def remove_key(provider: str):
    await delete_key(provider)
    return {"ok": True}

@app.post("/api/keys/{provider}/test", dependencies=[Depends(require_auth)])
async def test_key(provider: str):
    from .keys import get_key
    from ..gateway.registry import list_models
    from ..gateway.llm import complete
    key = await get_key(provider)
    if provider in ("tavily", "serper"):
        return {"ok": bool(key), "message": "Key saved." if key else "No key saved."}
    if not key and provider != "ollama":
        return {"ok": False, "message": "No key saved for this provider."}
    try:
        models = await list_models(provider, key)
        model = models[0] if models else None
        if not model:
            return {"ok": False, "message": "No models available for this provider."}
        await complete(provider, model, [{"role": "user", "content": "hi"}], key, max_tokens=1, timeout=20)
        return {"ok": True, "message": f"Key valid ({model})."}
    except Exception as e:
        from ..gateway.llm import redact_keys
        msg = str(e).lower()
        if "invalid" in msg or "401" in msg or "unauthorized" in msg:
            return {"ok": False, "message": "Invalid API key."}
        if "rate" in msg or "429" in msg:
            return {"ok": True, "message": "Key works (rate-limited right now)."}
        return {"ok": False, "message": redact_keys(f"Test failed: {str(e)[:120]}")}
