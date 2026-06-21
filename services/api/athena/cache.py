import hashlib
import json
import redis.asyncio as aioredis

from .config import settings

_client = None


def _r():
    global _client
    if _client is None:
        _client = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _client


def skey(prefix: str, *parts) -> str:
    h = hashlib.sha1("|".join(str(p) for p in parts).encode()).hexdigest()[:24]
    return f"{prefix}:{h}"


async def get_json(key: str):
    try:
        v = await _r().get(key)
        return json.loads(v) if v is not None else None
    except Exception:
        return None


async def set_json(key: str, value, ttl: int = 86400) -> None:
    try:
        await _r().set(key, json.dumps(value), ex=ttl)
    except Exception:
        pass
