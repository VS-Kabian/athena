import pytest
from unittest.mock import patch

from athena import migrate


def test_migration_files_sorted_and_include_known_migrations():
    names = [f.name for f in migrate.migration_files()]
    assert names == sorted(names)                      # numeric-prefix order
    assert "001_init.sql" in names and "005_memory.sql" in names


@pytest.mark.asyncio
async def test_apply_all_runs_every_file_in_order():
    applied_sql = []

    async def fake_exec(sql, *a):
        applied_sql.append(sql)

    with patch("athena.migrate.db.execute", side_effect=fake_exec):
        names = await migrate.apply_all()

    expected = [f.name for f in migrate.migration_files()]
    assert names == expected
    assert len(applied_sql) == len(expected)
    # the memory migration's content actually reached execute()
    assert any("research_memory" in sql for sql in applied_sql)
