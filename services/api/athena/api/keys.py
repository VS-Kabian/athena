import os
from pathlib import Path
from cryptography.fernet import Fernet
from ..db import fetch, execute
from ..config import settings
from ..log import get_logger

log = get_logger(__name__)

_KEY_PATH = Path(__file__).resolve().parents[2] / ".athena_key"

def _fernet() -> Fernet:
    # prefer the env-provided secret (survives redeploys); fall back to a local file for dev
    if settings.athena_secret:
        return Fernet(settings.athena_secret.encode())
    if _KEY_PATH.exists():
        key = _KEY_PATH.read_bytes()
    else:
        key = Fernet.generate_key()
        _KEY_PATH.write_bytes(key)
        try:
            os.chmod(_KEY_PATH, 0o600)   # owner-only — don't leave the vault master key world-readable
        except OSError:
            pass
    return Fernet(key)

def _mask(plain: str) -> str:
    if not plain:
        return ""
    if len(plain) <= 8:
        return "••••"
    return plain[:3] + "•" * 6 + plain[-4:]

async def set_key(provider: str, api_key: str) -> None:
    enc = _fernet().encrypt(api_key.strip().encode()).decode()
    await execute(
        """insert into api_keys(provider, key_enc, updated_at) values($1,$2,now())
           on conflict (provider) do update set key_enc=$2, updated_at=now()""",
        provider, enc,
    )

async def get_key(provider: str) -> str | None:
    rows = await fetch("select key_enc from api_keys where provider=$1", provider)
    if not rows:
        return None
    try:
        return _fernet().decrypt(rows[0]["key_enc"].encode()).decode()
    except Exception:
        # key was encrypted under a different secret (e.g. post-redeploy) OR the ciphertext is
        # corrupt — treat as unset, but surface it so a silent vault failure is observable.
        log.warning("could not decrypt stored key for provider '%s' (secret rotated or corrupt)", provider)
        return None

async def list_keys() -> list[dict]:
    rows = await fetch("select provider, key_enc from api_keys order by provider")
    f = _fernet()
    out = []
    for r in rows:
        try:
            plain = f.decrypt(r["key_enc"].encode()).decode()
        except Exception:
            continue  # skip rows we can't decrypt rather than 500 the whole vault
        out.append({"provider": r["provider"], "set": True, "masked": _mask(plain)})
    return out

async def delete_key(provider: str) -> None:
    await execute("delete from api_keys where provider=$1", provider)
