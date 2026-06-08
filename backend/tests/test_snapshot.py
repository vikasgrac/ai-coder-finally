"""Tests for the portfolio snapshot task."""
import pytest
from datetime import datetime, timezone, timedelta

import aiosqlite

from app.tasks.snapshot import record_snapshot, compute_total_value


class TestRecordSnapshot:
    async def test_inserts_snapshot_row(self, test_db):
        await record_snapshot(total_value=100000.0)
        async with aiosqlite.connect(test_db) as conn:
            async with conn.execute("SELECT COUNT(*) FROM portfolio_snapshots") as cur:
                row = await cur.fetchone()
                assert row[0] == 1

    async def test_snapshot_stores_correct_value(self, test_db):
        await record_snapshot(total_value=99999.0)
        async with aiosqlite.connect(test_db) as conn:
            async with conn.execute("SELECT total_value FROM portfolio_snapshots") as cur:
                row = await cur.fetchone()
                assert abs(row[0] - 99999.0) < 0.01

    async def test_old_snapshots_are_pruned(self, test_db):
        """Snapshots older than 24 h should be deleted on each write."""
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        async with aiosqlite.connect(test_db) as conn:
            import uuid
            await conn.execute(
                "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), "default", 50000.0, old_ts),
            )
            await conn.commit()

        # Writing a new snapshot should prune the old one
        await record_snapshot(total_value=100000.0)

        async with aiosqlite.connect(test_db) as conn:
            async with conn.execute(
                "SELECT COUNT(*) FROM portfolio_snapshots WHERE total_value = 50000.0"
            ) as cur:
                row = await cur.fetchone()
                assert row[0] == 0

    async def test_recent_snapshots_are_retained(self, test_db):
        await record_snapshot(total_value=100000.0)
        await record_snapshot(total_value=101000.0)
        async with aiosqlite.connect(test_db) as conn:
            async with conn.execute("SELECT COUNT(*) FROM portfolio_snapshots") as cur:
                row = await cur.fetchone()
                assert row[0] == 2
