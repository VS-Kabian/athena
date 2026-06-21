"""Apply database migrations idempotently.

Usage:
    python -m athena.migrate        # apply every migrations/*.sql in order, then list tables

Each migration uses `create ... if not exists`, so re-running is safe. Run this on a fresh
environment (or after pulling new migrations) before starting the API. Connection target comes
from the app config (DATABASE_URL), so no client tools (psql) are required.
"""
import asyncio
import pathlib

from . import db

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent / "migrations"


def migration_files() -> list[pathlib.Path]:
    """All migration SQL files, sorted by filename (numeric prefix = apply order)."""
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


async def apply_all() -> list[str]:
    """Apply every migration in order; returns the filenames applied."""
    applied = []
    for f in migration_files():
        await db.execute(f.read_text())
        applied.append(f.name)
    return applied


async def list_tables() -> list[str]:
    rows = await db.fetch("select table_name from information_schema.tables "
                          "where table_schema='public' order by table_name")
    return [r["table_name"] for r in rows]


async def main() -> None:
    files = migration_files()
    if not files:
        print(f"No migrations found in {MIGRATIONS_DIR}")
        return
    print(f"Applying {len(files)} migration(s) from {MIGRATIONS_DIR}:")
    try:
        for name in await apply_all():
            print(f"  OK  {name}")
        print("\nTables present: " + ", ".join(await list_tables()))
    finally:
        if db._pool is not None:
            await db._pool.close()


if __name__ == "__main__":
    asyncio.run(main())
