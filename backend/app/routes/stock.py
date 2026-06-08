"""
Stock detail endpoints — historical price data and quote stats.

History is generated via backward GBM from the current cached price so the
chart is always anchored to live data. If TAPETIDE_API_KEY is set, the quote
endpoint also pulls 52W stats from Tapetide; otherwise they are derived from
the synthetic 1Y history.
"""
import json
import logging
import math
import os
import random
from datetime import datetime, timezone, timedelta
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/stock", tags=["stock"])

# ---------------------------------------------------------------------------
# Period config: how many data points and what interval between them
# ---------------------------------------------------------------------------
_PERIOD_CFG = {
    "1d": {"n": 78,  "step_min": 5},       # 5-min bars  (~6.5 h trading day)
    "1w": {"n": 35,  "step_min": 60},      # hourly for 5 days
    "1m": {"n": 21,  "step_min": 60 * 7},  # daily for 21 trading days
    "6m": {"n": 126, "step_min": 60 * 7},  # daily for 6 months
    "1y": {"n": 252, "step_min": 60 * 7},  # daily for 1 year
    "5y": {"n": 260, "step_min": 60 * 24 * 5},  # weekly for 5 years
}

# Annual volatility proxy per ticker (rough estimate)
_ANNUAL_SIGMA = {
    "RELIANCE": 0.22, "TCS": 0.20, "INFY": 0.22, "HDFCBANK": 0.24,
    "ICICIBANK": 0.26, "HINDUNILVR": 0.18, "SBIN": 0.30, "WIPRO": 0.25,
    "BAJFINANCE": 0.32, "TATAMOTORS": 0.35,
}
_DEFAULT_SIGMA = 0.25
_TRADING_MINUTES_PER_YEAR = 252 * 7 * 60  # ~1,058,400


class HistoryPoint(BaseModel):
    time: str
    price: float


class StockQuoteDetail(BaseModel):
    ticker: str
    price: float
    week_52_high: float
    week_52_low: float
    prev_day_volume: Optional[int] = None
    prev_day_buy_volume: Optional[int] = None
    prev_day_sell_volume: Optional[int] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _current_price(ticker: str) -> float:
    """Return the latest cached price, falling back to simulator seed."""
    import app.main as app_state
    from app.market_data.simulator import SEED_PRICES, DEFAULT_SEED_PRICE

    provider = app_state.market_provider
    if provider:
        pd = provider.get_price(ticker)
        if pd:
            return pd.price
    return SEED_PRICES.get(ticker, DEFAULT_SEED_PRICE)


def _synthetic_history(ticker: str, period: str) -> List[HistoryPoint]:
    """
    Generate a backwards GBM price path anchored to the current live price.
    The RNG seed is deterministic per (ticker, period, UTC date) so charts
    look consistent within a day but shift each session.
    """
    cfg = _PERIOD_CFG.get(period, _PERIOD_CFG["1d"])
    n, step_min = cfg["n"], cfg["step_min"]
    current = _current_price(ticker)
    sigma_annual = _ANNUAL_SIGMA.get(ticker, _DEFAULT_SIGMA)
    dt = step_min / _TRADING_MINUTES_PER_YEAR
    sigma = sigma_annual * math.sqrt(dt)

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rng = random.Random(hash(f"{ticker}:{period}:{today}"))

    # Walk backwards: generate log-returns and reverse them
    prices = [current]
    for _ in range(n - 1):
        z = rng.gauss(0, 1)
        log_ret = (0.5 * sigma ** 2 * dt) + (sigma * z)  # reverse drift sign
        prices.append(max(prices[-1] / math.exp(log_ret), 0.01))
    prices.reverse()

    now = datetime.now(timezone.utc)
    return [
        HistoryPoint(
            time=(now - timedelta(minutes=(n - 1 - i) * step_min)).isoformat(),
            price=round(p, 2),
        )
        for i, p in enumerate(prices)
    ]


async def _tapetide_quote(ticker: str) -> Optional[Any]:
    """Call Tapetide get_stock_quote if API key is configured."""
    api_key = os.getenv("TAPETIDE_API_KEY", "")
    if not api_key:
        return None
    try:
        import fastmcp
        async with fastmcp.Client("https://mcp.tapetide.com/mcp", auth=api_key) as client:
            result = await client.call_tool("get_stock_quote", {"symbol": ticker})
            content = getattr(result, "content", None) or result
            if isinstance(content, list):
                for item in content:
                    text = getattr(item, "text", None)
                    if text:
                        try:
                            return json.loads(text)
                        except (json.JSONDecodeError, TypeError):
                            continue
            return None
    except Exception as exc:
        logger.warning("Tapetide quote fetch failed for %s: %s", ticker, exc)
        return None


def _parse_tapetide_quote(ticker: str, raw: Any, current: float) -> StockQuoteDetail:
    """Extract fields from a Tapetide get_stock_quote response."""
    if isinstance(raw, dict) and "data" in raw:
        raw = raw["data"]
    if isinstance(raw, list) and raw:
        raw = raw[0]
    if not isinstance(raw, dict):
        raw = {}

    def _f(keys: List[str], default: float) -> float:
        for k in keys:
            v = raw.get(k)
            if v is not None:
                try:
                    return float(v)
                except (ValueError, TypeError):
                    pass
        return default

    def _i(keys: List[str]) -> Optional[int]:
        for k in keys:
            v = raw.get(k)
            if v is not None:
                try:
                    return int(float(v))
                except (ValueError, TypeError):
                    pass
        return None

    h52 = _f(["week52High", "high52", "52w_high", "yearHigh"], current * 1.3)
    l52 = _f(["week52Low",  "low52",  "52w_low",  "yearLow"],  current * 0.7)
    vol = _i(["volume", "totalVolume", "tradedVolume"])
    buy_vol = _i(["buyVolume", "buy_quantity", "buyQty"])
    sell_vol = _i(["sellVolume", "sell_quantity", "sellQty"])

    return StockQuoteDetail(
        ticker=ticker,
        price=current,
        week_52_high=round(h52, 2),
        week_52_low=round(l52, 2),
        prev_day_volume=vol,
        prev_day_buy_volume=buy_vol,
        prev_day_sell_volume=sell_vol,
    )


def _synthetic_quote(ticker: str) -> StockQuoteDetail:
    """Derive 52W stats from 1Y synthetic history."""
    history = _synthetic_history(ticker, "1y")
    prices = [h.price for h in history]
    current = _current_price(ticker)

    rng = random.Random(hash(f"{ticker}:vol"))
    base_vol = int(current * rng.uniform(50_000, 300_000))
    buy_pct = rng.uniform(0.45, 0.55)

    return StockQuoteDetail(
        ticker=ticker,
        price=current,
        week_52_high=round(max(prices + [current]), 2),
        week_52_low=round(min(prices + [current]), 2),
        prev_day_volume=base_vol,
        prev_day_buy_volume=int(base_vol * buy_pct),
        prev_day_sell_volume=int(base_vol * (1 - buy_pct)),
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/{ticker}/history", response_model=List[HistoryPoint])
async def get_history(ticker: str, period: str = "1d"):
    """
    Return price history for a ticker over the requested period.
    Always uses synthetic GBM data anchored to the current live price.
    """
    ticker = ticker.upper()
    if period not in _PERIOD_CFG:
        raise HTTPException(status_code=422, detail=f"Invalid period. Use: {', '.join(_PERIOD_CFG)}")
    return _synthetic_history(ticker, period)


@router.get("/{ticker}/quote", response_model=StockQuoteDetail)
async def get_quote_detail(ticker: str):
    """
    Return 52W high/low, volume, and buy/sell breakdown.
    Uses Tapetide if TAPETIDE_API_KEY is set, otherwise synthetic data.
    """
    ticker = ticker.upper()
    current = _current_price(ticker)

    raw = await _tapetide_quote(ticker)
    if raw is not None:
        return _parse_tapetide_quote(ticker, raw, current)
    return _synthetic_quote(ticker)
