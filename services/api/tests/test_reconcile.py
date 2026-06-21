import pytest
from unittest.mock import patch, AsyncMock
from athena.api.app import reconcile_stale_runs


@pytest.mark.asyncio
async def test_reconcile_marks_stale_running_failed():
    ex = AsyncMock()
    with patch("athena.api.app.execute", ex):
        await reconcile_stale_runs()
    sql = ex.call_args[0][0].lower()
    assert "update research_runs set status='failed'" in sql
    assert "status='running'" in sql and "interval" in sql


@pytest.mark.asyncio
async def test_reconcile_swallows_db_errors():
    with patch("athena.api.app.execute", AsyncMock(side_effect=RuntimeError("db down"))):
        await reconcile_stale_runs()  # must not raise
