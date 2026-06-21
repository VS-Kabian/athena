import asyncio

import asyncpg

from .config import settings
from .log import get_logger

log = get_logger(__name__)
_pool: asyncpg.Pool | None = None
_pool_lock: asyncio.Lock | None = None


def _lock() -> asyncio.Lock:
    global _pool_lock
    if _pool_lock is None:           # lazily bound to the running loop
        _pool_lock = asyncio.Lock()
    return _pool_lock


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        async with _lock():          # serialize creation so concurrent callers can't leak a 2nd pool
            if _pool is None:
                _pool = await asyncpg.create_pool(settings.database_url, min_size=1, max_size=10,
                                                  command_timeout=30, timeout=10)
    return _pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def _run(method: str, q: str, *args):
    """Run a query, retrying ONCE on a connection-level error (reset the pool, reconnect) so a
    transient DB blip self-heals instead of surfacing a raw ConnectionRefusedError."""
    global _pool
    for attempt in range(2):
        pool = await get_pool()
        try:
            async with pool.acquire() as c:
                return await getattr(c, method)(q, *args)
        except (asyncpg.PostgresConnectionError, ConnectionError, OSError) as e:
            log.warning("db %s failed (attempt %d/2): %s", method, attempt + 1, e)
            # Only tear down the SAME pool generation that failed — under the lock — so a concurrent
            # coroutine that already rebuilt a fresh pool isn't closed out from under its in-flight
            # queries (a late failure must not reset a newer pool).
            async with _lock():
                if _pool is pool:
                    try:
                        await pool.close()
                    except Exception:
                        pass
                    _pool = None
            if attempt == 1:
                raise


async def fetch(q: str, *args):
    return await _run("fetch", q, *args)


async def execute(q: str, *args):
    return await _run("execute", q, *args)
