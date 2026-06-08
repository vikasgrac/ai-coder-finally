"""Watchlist CRUD endpoints."""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.database import get_db
import app.main as app_state

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class AddTickerRequest(BaseModel):
    ticker: str


@router.get("")
async def get_watchlist():
    prices = {}
    if app_state.market_provider is not None:
        prices = app_state.market_provider.get_all_prices()

    async for conn in get_db():
        async with conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = 'default' ORDER BY added_at"
        ) as cursor:
            rows = await cursor.fetchall()

    result = []
    for row in rows:
        ticker = row["ticker"]
        price_data = prices.get(ticker)
        result.append({
            "ticker": ticker,
            "price": price_data.price if price_data else None,
            "previous_price": price_data.previous_price if price_data else None,
            "change_direction": price_data.change_direction if price_data else None,
            "timestamp": price_data.timestamp if price_data else None,
        })
    return result


@router.post("", status_code=201)
async def add_ticker(body: AddTickerRequest):
    ticker = body.ticker.strip().upper()
    if not ticker:
        raise HTTPException(status_code=422, detail="ticker must not be empty")

    async for conn in get_db():
        try:
            await conn.execute(
                "INSERT INTO watchlist (id, user_id, ticker, added_at) VALUES (?, ?, ?, ?)",
                (str(uuid.uuid4()), "default", ticker, _now()),
            )
            await conn.commit()
        except Exception as e:
            if "UNIQUE constraint" in str(e):
                raise HTTPException(status_code=409, detail=f"{ticker} already in watchlist")
            raise

    if app_state.market_provider is not None:
        await app_state.market_provider.add_ticker(ticker)

    return {"ticker": ticker}


@router.delete("/{ticker}", status_code=200)
async def remove_ticker(ticker: str):
    ticker = ticker.strip().upper()

    async for conn in get_db():
        async with conn.execute(
            "SELECT id FROM watchlist WHERE user_id = 'default' AND ticker = ?", (ticker,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"{ticker} not in watchlist")

        await conn.execute(
            "DELETE FROM watchlist WHERE user_id = 'default' AND ticker = ?", (ticker,)
        )
        await conn.commit()

    if app_state.market_provider is not None:
        await app_state.market_provider.remove_ticker(ticker)

    return {"ticker": ticker}
