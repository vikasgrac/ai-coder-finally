"""Tests for database initialization and seeding."""
import pytest
import aiosqlite
from pathlib import Path

from schema.seed import DEFAULT_WATCHLIST, seed_default_data
from app.database import init_db, set_db_path


@pytest.fixture
async def db_path(tmp_path):
    path = tmp_path / "test_finally.db"
    set_db_path(path)
    yield path
    set_db_path(None)


async def get_tables(path: Path) -> set[str]:
    async with aiosqlite.connect(path) as conn:
        async with conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ) as cur:
            rows = await cur.fetchall()
            return {row[0] for row in rows}


class TestSchemaCreation:
    async def test_all_tables_created(self, db_path):
        await init_db(db_path)
        tables = await get_tables(db_path)
        expected = {
            "users_profile", "watchlist", "positions",
            "trades", "portfolio_snapshots", "chat_messages",
        }
        assert expected.issubset(tables)

    async def test_idempotent_init(self, db_path):
        """Running init twice should not raise or duplicate data."""
        await init_db(db_path)
        await init_db(db_path)
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute("SELECT COUNT(*) FROM users_profile") as cur:
                row = await cur.fetchone()
                assert row[0] == 1


class TestSeedData:
    async def test_default_user_exists(self, db_path):
        await init_db(db_path)
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute(
                "SELECT cash_balance FROM users_profile WHERE id = 'default'"
            ) as cur:
                row = await cur.fetchone()
                assert row is not None
                assert row[0] == 100000.0

    async def test_default_watchlist_tickers(self, db_path):
        await init_db(db_path)
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute(
                "SELECT ticker FROM watchlist WHERE user_id = 'default'"
            ) as cur:
                rows = await cur.fetchall()
                tickers = {row[0] for row in rows}
                assert tickers == set(DEFAULT_WATCHLIST)

    async def test_seed_idempotent(self, db_path):
        """Seeding twice should not create duplicate rows."""
        await init_db(db_path)
        # Seed again manually
        async with aiosqlite.connect(db_path) as conn:
            await seed_default_data(conn)
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM watchlist WHERE user_id = 'default'"
            ) as cur:
                row = await cur.fetchone()
                assert row[0] == len(DEFAULT_WATCHLIST)

    async def test_watchlist_has_exactly_ten_tickers(self, db_path):
        await init_db(db_path)
        async with aiosqlite.connect(db_path) as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM watchlist WHERE user_id = 'default'"
            ) as cur:
                row = await cur.fetchone()
                assert row[0] == 10
