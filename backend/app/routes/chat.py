"""Chat endpoint: LLM integration with auto-execution of trades and watchlist changes."""
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

import app.main as app_state
from app.database import get_db
from app.llm.client import call_llm
from app.llm.context import build_messages

router = APIRouter(prefix="/api/chat", tags=["chat"])
_HISTORY_LIMIT = 20  # number of recent messages to include


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ChatRequest(BaseModel):
    message: str


async def _get_portfolio_snapshot() -> dict:
    """Build portfolio context dict for the LLM."""
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
            pos_rows = await cur.fetchall()

        async with conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = 'default' ORDER BY added_at"
        ) as cur:
            wl_rows = await cur.fetchall()

    positions = []
    total_pos_value = 0.0
    for row in pos_rows:
        pd = provider.get_price(row["ticker"]) if provider else None
        current_price = pd.price if pd else row["avg_cost"]
        unrealized_pnl = (current_price - row["avg_cost"]) * row["quantity"]
        pct_change = (
            (current_price - row["avg_cost"]) / row["avg_cost"] * 100
            if row["avg_cost"] > 0 else 0.0
        )
        positions.append({
            "ticker": row["ticker"],
            "quantity": row["quantity"],
            "avg_cost": row["avg_cost"],
            "current_price": current_price,
            "unrealized_pnl": unrealized_pnl,
            "pct_change": pct_change,
        })
        total_pos_value += current_price * row["quantity"]

    watchlist = []
    for row in wl_rows:
        pd = provider.get_price(row["ticker"]) if provider else None
        watchlist.append({"ticker": row["ticker"], "price": pd.price if pd else None})

    return {
        "cash": cash,
        "positions": positions,
        "total_value": cash + total_pos_value,
        "watchlist": watchlist,
    }


async def _execute_trade(ticker: str, side: str, quantity: float) -> dict:
    """Execute a trade and return result dict."""
    provider = app_state.market_provider
    price_data = provider.get_price(ticker) if provider else None
    if not price_data:
        return {"ticker": ticker, "error": "no price available"}

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
                return {"ticker": ticker, "error": "insufficient cash"}
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
        elif side == "sell":
            if not position:
                return {"ticker": ticker, "error": "no position to sell"}
            held = position["quantity"]
            if quantity > held:
                return {"ticker": ticker, "error": "insufficient shares"}
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
        else:
            return {"ticker": ticker, "error": f"unknown side: {side}"}

        await conn.execute(
            "UPDATE users_profile SET cash_balance = ? WHERE id = 'default'", (new_cash,)
        )
        await conn.execute(
            "INSERT INTO trades (id, user_id, ticker, side, quantity, price, executed_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "default", ticker, side, quantity, price, _now()),
        )
        await conn.commit()

    return {"ticker": ticker, "side": side, "quantity": quantity, "price": price}


async def _execute_watchlist_change(ticker: str, action: str) -> dict:
    """Add or remove a ticker from the watchlist."""
    ticker = ticker.strip().upper()
    provider = app_state.market_provider

    async for conn in get_db():
        if action == "add":
            try:
                await conn.execute(
                    "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                    (str(uuid.uuid4()), "default", ticker, _now()),
                )
                await conn.commit()
                if provider:
                    await provider.add_ticker(ticker)
            except Exception as e:
                if "UNIQUE constraint" not in str(e):
                    raise
        elif action == "remove":
            await conn.execute(
                "DELETE FROM watchlist WHERE user_id = 'default' AND ticker = ?", (ticker,)
            )
            await conn.commit()
            if provider:
                await provider.remove_ticker(ticker)

    return {"ticker": ticker, "action": action}


@router.post("")
async def chat(body: ChatRequest):
    user_message = body.message.strip()
    if not user_message:
        raise HTTPException(status_code=422, detail="message must not be empty")

    # Load conversation history
    async for conn in get_db():
        async with conn.execute(
            "SELECT role, content FROM chat_messages WHERE user_id = 'default' "
            "ORDER BY created_at DESC LIMIT ?",
            (_HISTORY_LIMIT,),
        ) as cur:
            rows = await cur.fetchall()
    history = list(reversed([{"role": r["role"], "content": r["content"]} for r in rows]))

    portfolio = await _get_portfolio_snapshot()
    messages = build_messages(portfolio, history, user_message)

    # Call LLM (or mock)
    llm_response = await call_llm(messages)

    # Auto-execute trades
    trade_results = []
    for trade in llm_response.trades:
        result = await _execute_trade(trade.ticker.upper(), trade.side, trade.quantity)
        trade_results.append(result)

    # Auto-execute watchlist changes
    wl_results = []
    for change in llm_response.watchlist_changes:
        result = await _execute_watchlist_change(change.ticker, change.action)
        wl_results.append(result)

    actions = {"trades": trade_results, "watchlist_changes": wl_results}

    # Persist both messages
    async for conn in get_db():
        await conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "default", "user", user_message, None, _now()),
        )
        await conn.execute(
            "INSERT INTO chat_messages (id, user_id, role, content, actions, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "default", "assistant", llm_response.message,
             json.dumps(actions), _now()),
        )
        await conn.commit()

    return {
        "message": llm_response.message,
        "actions": actions,
    }
