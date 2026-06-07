# Market Data Interface

This document defines the unified Python interface for market data in FinAlly, and describes how the backend selects between the live Massive API poller and the built-in simulator.

---

## Design Goals

- All downstream code (SSE streaming, portfolio P&L, frontend) is agnostic to the data source
- Switching between live data and simulation requires only an environment variable change — no code changes
- The interface is minimal: write prices into a shared cache; let everything else read from it
- Both implementations run as a background async task inside the FastAPI process

---

## The Price Cache

The shared in-memory price cache is the single point of truth for current prices. Both the simulator and the Massive poller write to it. SSE streams and API endpoints read from it.

```python
# backend/market/cache.py

from dataclasses import dataclass, field
from datetime import datetime
import asyncio

@dataclass
class PriceEntry:
    ticker: str
    price: float
    prev_price: float
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def change_pct(self) -> float:
        if self.prev_price == 0:
            return 0.0
        return (self.price - self.prev_price) / self.prev_price * 100

    @property
    def direction(self) -> str:
        if self.price > self.prev_price:
            return "up"
        if self.price < self.prev_price:
            return "down"
        return "flat"


class PriceCache:
    def __init__(self):
        self._prices: dict[str, PriceEntry] = {}
        self._lock = asyncio.Lock()

    async def update(self, ticker: str, price: float) -> PriceEntry:
        async with self._lock:
            prev = self._prices.get(ticker)
            prev_price = prev.price if prev else price
            entry = PriceEntry(ticker=ticker, price=price, prev_price=prev_price)
            self._prices[ticker] = entry
            return entry

    def get(self, ticker: str) -> PriceEntry | None:
        return self._prices.get(ticker)

    def get_all(self) -> dict[str, PriceEntry]:
        return dict(self._prices)

    def tickers(self) -> list[str]:
        return list(self._prices.keys())


# Module-level singleton — imported everywhere
price_cache = PriceCache()
```

---

## Abstract Interface

```python
# backend/market/base.py

from abc import ABC, abstractmethod

class MarketDataSource(ABC):
    """
    Background task that continuously writes prices into the shared PriceCache.
    Instantiate once; call start() to begin the update loop.
    """

    @abstractmethod
    async def start(self, tickers: list[str]) -> None:
        """Start the polling/simulation loop. Runs until the process exits."""
        ...

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the active set at runtime (called when user adds to watchlist)."""
        ...

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker from the active set (called when user removes from watchlist)."""
        ...
```

---

## Factory — Environment-Based Selection

```python
# backend/market/factory.py

import os
from .base import MarketDataSource
from .simulator import MarketSimulator
from .massive import MassivePoller


def create_market_data_source() -> MarketDataSource:
    """
    Returns a MassivePoller if MASSIVE_API_KEY is set and non-empty,
    otherwise returns the built-in MarketSimulator.
    """
    api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
    if api_key:
        return MassivePoller(api_key=api_key)
    return MarketSimulator()
```

This factory is called once at FastAPI startup:

```python
# backend/main.py (startup)

from contextlib import asynccontextmanager
from fastapi import FastAPI
from market.factory import create_market_data_source
from market.cache import price_cache
from db import get_watchlist_tickers

market_source: MarketDataSource | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global market_source
    tickers = await get_watchlist_tickers()  # load from DB on startup
    market_source = create_market_data_source()
    import asyncio
    asyncio.create_task(market_source.start(tickers))
    yield
    # shutdown: the task is cancelled automatically

app = FastAPI(lifespan=lifespan)
```

---

## MassivePoller Implementation

Polls the Massive snapshot endpoint every ~10 seconds to anchor prices to real market values. Between polls, applies low-volatility GBM micro-moves to keep the UI lively.

```python
# backend/market/massive.py

import asyncio
import httpx
import math
import random
from datetime import datetime
from .base import MarketDataSource
from .cache import price_cache

SNAPSHOT_URL = "https://api.polygon.io/v2/snapshot/locale/us/markets/stocks/tickers"
POLL_INTERVAL_S = 10       # seconds between Massive API calls
MICRO_INTERVAL_S = 0.5     # seconds between GBM micro-moves
MICRO_VOLATILITY = 0.0005  # annualized vol ÷ sqrt(seconds_per_year) — very small


class MassivePoller(MarketDataSource):
    def __init__(self, api_key: str):
        self._api_key = api_key
        self._tickers: set[str] = set()
        self._lock = asyncio.Lock()

    async def start(self, tickers: list[str]) -> None:
        async with self._lock:
            self._tickers = set(tickers)

        await asyncio.gather(
            self._poll_loop(),
            self._micro_move_loop(),
        )

    async def add_ticker(self, ticker: str) -> None:
        async with self._lock:
            self._tickers.add(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        async with self._lock:
            self._tickers.discard(ticker)

    async def _poll_loop(self) -> None:
        async with httpx.AsyncClient(timeout=15) as client:
            while True:
                tickers = list(self._tickers)
                if tickers:
                    try:
                        await self._fetch_and_update(client, tickers)
                    except Exception as e:
                        print(f"[MassivePoller] poll error: {e}")
                await asyncio.sleep(POLL_INTERVAL_S)

    async def _fetch_and_update(self, client: httpx.AsyncClient, tickers: list[str]) -> None:
        params = {
            "tickers": ",".join(tickers),
            "apiKey": self._api_key,
        }
        r = await client.get(SNAPSHOT_URL, params=params)
        r.raise_for_status()
        data = r.json()

        if data.get("status") not in ("OK", "DELAYED"):
            raise RuntimeError(f"Massive API: {data.get('error', data)}")

        for snap in data.get("tickers", []):
            ticker = snap["ticker"]
            # Prefer lastTrade price; fall back to day close
            last_trade = snap.get("lastTrade", {})
            price = last_trade.get("p") or snap.get("day", {}).get("c")
            if price:
                await price_cache.update(ticker, float(price))

    async def _micro_move_loop(self) -> None:
        """Apply tiny GBM perturbations between real polls to keep price flash animations firing."""
        dt = MICRO_INTERVAL_S / (252 * 6.5 * 3600)  # fraction of a trading year
        while True:
            await asyncio.sleep(MICRO_INTERVAL_S)
            for ticker, entry in price_cache.get_all().items():
                drift = 0.0
                shock = MICRO_VOLATILITY * math.sqrt(dt) * random.gauss(0, 1)
                new_price = entry.price * math.exp((drift - 0.5 * MICRO_VOLATILITY**2) * dt + shock)
                await price_cache.update(ticker, round(new_price, 2))
```

---

## SSE Stream Endpoint

The SSE endpoint reads from the cache and pushes updates to all connected clients at a fixed cadence. It is identical regardless of which `MarketDataSource` is running.

```python
# backend/routes/stream.py

import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from market.cache import price_cache

router = APIRouter()

@router.get("/api/stream/prices")
async def stream_prices():
    async def event_generator():
        while True:
            prices = price_cache.get_all()
            for ticker, entry in prices.items():
                payload = {
                    "ticker": ticker,
                    "price": entry.price,
                    "prev_price": entry.prev_price,
                    "change_pct": round(entry.change_pct, 3),
                    "direction": entry.direction,
                    "timestamp": entry.timestamp.isoformat(),
                }
                yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
```

---

## Watchlist API Integration

When the user adds or removes a ticker via the API, the market data source is notified immediately so prices start (or stop) updating without a restart.

```python
# backend/routes/watchlist.py (excerpt)

from market.factory import market_source  # the running instance

@router.post("/api/watchlist")
async def add_ticker(body: AddTickerRequest):
    await db_add_ticker(body.ticker)
    await market_source.add_ticker(body.ticker)
    return {"ticker": body.ticker}

@router.delete("/api/watchlist/{ticker}")
async def remove_ticker(ticker: str):
    await db_remove_ticker(ticker)
    await market_source.remove_ticker(ticker)
    return {"ticker": ticker}
```

---

## Directory Structure

```
backend/
└── market/
    ├── __init__.py
    ├── base.py          # MarketDataSource abstract class
    ├── cache.py         # PriceCache + PriceEntry
    ├── factory.py       # create_market_data_source()
    ├── massive.py       # MassivePoller (live API)
    └── simulator.py     # MarketSimulator (GBM-based)
```

---

## Environment Variable Summary

| Variable | Effect |
|---|---|
| `MASSIVE_API_KEY` set | Uses `MassivePoller` with live/delayed US equity prices |
| `MASSIVE_API_KEY` absent or empty | Uses `MarketSimulator` (no external dependencies) |

The `.env.example` file should document this with:

```
# Optional: Massive API key for live US equity prices
# Leave blank to use the built-in simulator (recommended for most users)
MASSIVE_API_KEY=
```
