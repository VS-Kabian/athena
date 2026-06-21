"""Shared test fixtures.

pytest-asyncio (auto mode) runs each test on its own event loop. The asyncpg pool in
`athena.db` is a module-global created lazily on first use, bound to whatever loop was
active then. Reusing it from a later test's loop raises cross-loop errors. So we close
and reset the pool after every test — each test gets a fresh pool on its own loop.
"""
import pytest

import athena.db as db


@pytest.fixture(autouse=True)
async def _reset_db_pool():
    yield
    if db._pool is not None:
        try:
            await db._pool.close()
        finally:
            db._pool = None


@pytest.fixture(autouse=True)
async def _reset_redis():
    yield
    import athena.cache as c
    if c._client is not None:
        try:
            await c._client.aclose()
        except Exception:
            pass
        c._client = None


@pytest.fixture(autouse=True)
def _mock_is_safe_url(request):
    path = request.node.fspath.strpath
    if "test_fetch" not in path and "test_hardening_pass" not in path and "test_security_fixes" not in path:
        from unittest.mock import patch
        with patch("athena.fetch._is_safe_url", return_value=True):
            yield
    else:
        yield


@pytest.fixture(autouse=True)
def _stub_trust_network(request):
    """Several pipeline steps do real network I/O or model calls — the URL-liveness probe (`check_urls`),
    entailment (`entail_report`), and multi-hop chasing (`hop.chase`). Stub them at the integration
    boundary by default so full-pipeline tests stay fast and offline-deterministic — like the
    `_is_safe_url` auto-mock above. Tests that exercise these directly patch their own internals, so the
    relevant stub is skipped for them (test_entail/test_urlhealth/test_trust for entail+urls, test_hop
    for chasing)."""
    from contextlib import ExitStack
    from unittest.mock import patch, AsyncMock
    path = request.node.fspath.strpath
    _benign_entail = {"engine": "embedding", "risk": 0.0, "total": 0, "supported": 0, "refuted": 0,
                      "nei": 0, "conflicts": 0, "conflict_items": [], "verdicts": [], "flagged": [],
                      "coverage": 0.0}
    patches = []
    if not any(x in path for x in ("test_urlhealth", "test_entail", "test_trust")):
        patches.append(patch("athena.agents.graph.check_urls", new=AsyncMock(return_value={})))
        patches.append(patch("athena.agents.graph.entail_report", new=AsyncMock(return_value=_benign_entail)))
    if "test_hop" not in path:
        patches.append(patch("athena.agents.hop.chase", new=AsyncMock(return_value=0)))
    try:
        with ExitStack() as stack:
            for p in patches:
                stack.enter_context(p)
            yield
    except (ImportError, AttributeError):
        yield
