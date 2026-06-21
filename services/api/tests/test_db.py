import pytest

from athena.db import fetch


@pytest.mark.asyncio
async def test_tables_exist():
    rows = await fetch(
        "select table_name from information_schema.tables where table_schema='public'"
    )
    names = {r["table_name"] for r in rows}
    assert {"research_runs", "sources", "reports"} <= names
