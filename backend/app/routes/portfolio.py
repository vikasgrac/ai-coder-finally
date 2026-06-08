"""Portfolio endpoints: positions, trade execution, P&L history."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import app.main as app_state
from app.database import get_db
from app.tasks.snapshot import record_snapshot

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class TradeRequest(BaseModel):
    ticker: str
    side: str   # "buy" | "sell"
    quantity: float


def _build_position_row(row, price_data) -> dict:
    current_price = price_data.price if price_data else row["avg_cost"]
    unrealized_pnl = (current_price - row["avg_cost"]) * row["quantity"]
    pct_change = (
        (current_price - row["avg_cost"]) / row["avg_cost"] * 100
        if row["avg_cost"] > 0 else 0.0
    )
    return {
        "ticker": row["ticker"],
        "quantity": row["quantity"],
        "avg_cost": row["avg_cost"],
        "current_price": current_price,
        "unrealized_pnl": unrealized_pnl,
        "pct_change": pct_change,
    }


@router.get("")
async def get_portfolio():
    provider = app_state.market_provider

    async for conn in get_db():
        async with conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = 'default'"
        ) as cur:
            profile = await cur.fetchone()
        cash = profile["cash_balance"] if profile else 100000.0

        async with conn.execute(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id = 'default'"
        ) as cur:
            position_rows = await cur.fetchall()

    positions = []
    total_position_value = 0.0
    for row in position_rows:
        price_data = provider.get_price(row["ticker"]) if provider else None
        pos = _build_position_row(row, price_data)
        positions.append(pos)
        total_position_value += pos["current_price"] * row["quantity"]

    return {
        "cash": cash,
        "positions": positions,
        "total_value": cash + total_position_value,
    }


@router.post("/trade")
async def execute_trade(body: TradeRequest):
    ticker = body.ticker.strip().upper()
    side = body.side.lower()
    quantity = body.quantity

    if side not in ("buy", "sell"):
        raise HTTPException(status_code=422, detail="side must be 'buy' or 'sell'")
    if quantity <= 0:
        raise HTTPException(status_code=422, detail="quantity must be positive")

    provider = app_state.market_provider
    price_data = provider.get_price(ticker) if provider else None
    if price_data is None:
        # Use a default if ticker not tracked — add it so future SSE covers it
        if provider:
            await provider.add_ticker(ticker)
            price_data = provider.get_price(ticker)
        if price_data is None:
            raise HTTPException(status_code=404, detail=f"No price available for {ticker}")
    price = price_data.price

    async for conn in get_db():
        async with conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = 'default'"
        ) as cur:
            profile = await cur.fetchone()
        cash = profile["cash_balance"]

        async with conn.execute(
            "SELECT quantity, avg_cost FROM positions WHERE user_id = 'default' AND ticker = ?",
            (ticker,),
        ) as cur:
            position = await cur.fetchone()

        if side == "buy":
            cost = price * quantity
            if cost > cash:
                raise HTTPException(status_code=400, detail="Insufficient cash")
            new_cash = cash - cost
            if position:
                old_qty = position["quantity"]
                old_avg = position["avg_cost"]
                new_qty = old_qty + quantity
                new_avg = (old_qty * old_avg + quantity * price) / new_qty
                await conn.execute(
                    "UPDATE positions SET quantity = ?, avg_cost = ?, updated_at = ? "
                    "WHERE user_id = 'default' AND ticker = ?",
                    (new_qty, new_avg, _now(), ticker),
                )
            else:
                await conn.execute(
                    "INSERT INTO positions (id, user_id, ticker, quantity, avg_cost, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (str(uuid.uuid4()), "default", ticker, quantity, price, _now()),
                )
        else:  # sell
            if position is None:
                raise HTTPException(status_code=400, detail=f"No position in {ticker}")
            held = position["quantity"]
            if quantity > held:
                raise HTTPException(status_code=400, detail="Insufficient shares")
            new_cash = cash + price * quantity
            new_qty = held - quantity
            if new_qty < 1e-9:
                await conn.execute(
                    "DELETE FROM positions WHERE user_id = 'default' AND ticker = ?", (ticker,)
                )
            else:
                await conn.execute(
                    "UPDATE positions SET quantity = ?, updated_at = ? "
                    "WHERE user_id = 'default' AND ticker = ?",
                    (new_qty, _now(), ticker),
                )

        await conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = 'default'", (new_cash,)
        )
        await conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "default", ticker, side, quantity, price, _now()),
        )
        await conn.commit()

    # Record snapshot after trade
    async for conn in get_db():
        async with conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id = 'default'"
        ) as cur:
            row = await cur.fetchone()
            updated_cash = row["cash_balance"]
        async with conn.execute(
            "SELECT ticker, quantity FROM positions WHERE user_id = 'default'"
        ) as cur:
            updated_positions = await cur.fetchall()

    total_position_value = sum(
        (provider.get_price(p["ticker"]).price if provider and provider.get_price(p["ticker"]) else 0) * p["quantity"]
        for p in updated_positions
    )
    await record_snapshot(updated_cash + total_position_value)

    return {"ticker": ticker, "side": side, "quantity": quantity, "price": price}


@router.get("/history")
async def get_portfolio_history():
    from datetime import timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    async for conn in get_db():
        async with conn.execute(
            "SELECT total_value, recorded_at FROM portfolio_snapshots "
            "WHERE user_id = 'default' AND recorded_at >= ? ORDER BY recorded_at",
            (cutoff,),
        ) as cur:
            rows = await cur.fetchall()

    return [{"total_value": row["total_value"], "recorded_at": row["recorded_at"]} for row in rows]
