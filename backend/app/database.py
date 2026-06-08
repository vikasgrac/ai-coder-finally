"""Async SQLite helpers with lazy schema init and seeding."""
import os
from pathlib import Path
from typing import AsyncIterator

import aiosqlite

from schema.seed import DEFAULT_WATCHLIST, seed_default_data

_DB_PATH: Path | None = None


def get_db_path() -> Path:
    """Resolve the database file path from environment or project default."""
    global _DB_PATH
    if _DB_PATH is not None:
        return _DB_PATH
    env_val = os.getenv("DB_PATH", "")
    if env_val:
        return Path(env_val)
    # Default: <project-root>/db/finally.db (two levels up from backend/)
    backend_dir = Path(__file__).parent.parent
    return backend_dir.parent / "db" / "finally.db"


def set_db_path(path: Path | None) -> None:
    """Override the database path (used in tests). Pass None to reset to default."""
    global _DB_PATH
    _DB_PATH = path


_SCHEMA_SQL = Path(__file__).parent.parent / "schema" / "schema.sql"


async def init_db(db_path: Path | None = None) -> None:
    """Create schema and seed default data if the database is empty."""
    path = db_path or get_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    schema = _SCHEMA_SQL.read_text()
    async with aiosqlite.connect(path) as conn:
        await conn.executescript(schema)
        await conn.commit()
        await seed_default_data(conn)


async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """Async context manager yielding a connected aiosqlite connection."""
    path = get_db_path()
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = aiosqlite.Row
        yield conn
