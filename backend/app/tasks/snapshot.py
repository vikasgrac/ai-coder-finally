"""Background task: record portfolio value snapshots every 30 s, prune to 24 h."""
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta

import aiosqlite

from app.database import get_db

logger = logging.getLogger(__name__)

_SNAPSHOT_INTERVAL = 30  # seconds
_RETENTION_HOURS = 24


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cutoff() -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=_RETENTION_HOURS)).isoformat()


async def record_snapshot(total_value: float, user_id: str = "default") -> None:
    """Insert one portfolio value snapshot and prune rows older than 24 h."""
    async for conn in get_db():
        await conn.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), user_id, total_value, _now()),
        )
        await conn.execute(
            "DELETE FROM portfolio_snapshots WHERE user_id = ? AND recorded_at < ?",
            (user_id, _cutoff()),
        )
        await conn.commit()


async def compute_total_value(user_id: str = "default") -> float:
    """Compute total portfolio value (cash + positions at current market prices)."""
    import app.main as app_state

    async for conn in get_db():
        async with conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = ?", (user_id,)
        ) as cur:
            row = await cur.fetchone()
            cash = row["cash_balance"] if row else 0.0

        async with conn.execute(
            "SELECT ticker, quantity FROM positions WHERE user_id = ?", (user_id,)
        ) as cur:
            positions = await cur.fetchall()

    total = cash
    provider = app_state.market_provider
    for pos in positions:
        price_data = provider.get_price(pos["ticker"]) if provider else None
        price = price_data.price if price_data else 0.0
        total += pos["quantity"] * price

    return total


async def run_snapshot_loop() -> None:
    """Periodically record portfolio snapshots until the task is cancelled."""
    while True:
        try:
            total = await compute_total_value()
            await record_snapshot(total)
        except Exception as exc:
            logger.warning("Portfolio snapshot failed: %s", exc)
        await asyncio.sleep(_SNAPSHOT_INTERVAL)
