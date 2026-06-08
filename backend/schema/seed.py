"""Seed default data into a fresh database."""
import uuid
from datetime import datetime, timezone

DEFAULT_WATCHLIST = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "HINDUNILVR", "SBIN", "WIPRO", "BAJFINANCE", "TATAMOTORS",
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


async def seed_default_data(conn) -> None:
    """Insert default user and watchlist if not already present. Idempotent."""
    await conn.execute(
        "INSERT OR IGNORE INTO users_profile (id, cash_balance, created_at) VALUES (?, ?, ?)",
        ("default", 100000.0, _now()),
    )
    for ticker in DEFAULT_WATCHLIST:
        await conn.execute(
            "INSERT OR IGNORE INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
            (str(uuid.uuid4()), "default", ticker, _now()),
        )
    await conn.commit()
