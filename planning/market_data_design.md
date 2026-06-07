# Market Data Backend — Design Document

## Overview

The market data layer is a self-contained subsystem inside the FastAPI backend.
It is responsible for maintaining an in-memory price cache and streaming updates
to connected SSE clients. Two implementations are provided behind a single
abstract interface; the active implementation is selected at startup from the
`TAPETIDE_API_KEY` environment variable.

```
                        ┌──────────────────────┐
                        │   MarketDataInterface │  (abstract base)
                        └──────────┬───────────┘
                                   │ implements
              ┌────────────────────┴──────────────────────┐
              │                                            │
   ┌──────────▼──────────┐                   ┌────────────▼────────────┐
   │   GBMSimulator      │                   │   TapetidePoller        │
   │  (always available) │                   │  (TAPETIDE_API_KEY set) │
   └──────────┬──────────┘                   └────────────┬────────────┘
              │                                            │
              └────────────────────┬───────────────────────┘
                                   │ writes
                          ┌────────▼────────┐
                          │   PriceCache    │  (in-memory dict, thread-safe)
                          └────────┬────────┘
                                   │ read by
                        ┌──────────▼───────────┐
                        │  SSE /api/stream/prices│
                        └──────────────────────┘
```

---

## File Layout

```
backend/
├── pyproject.toml
├── uv.lock
└── app/
    ├── main.py                # FastAPI app, startup/shutdown lifecycle
    ├── config.py              # Settings from environment variables
    ├── database.py            # SQLite init, WAL mode, schema, seed
    ├── market/
    │   ├── __init__.py
    │   ├── interface.py       # MarketDataInterface ABC + PriceEntry dataclass
    │   ├── cache.py           # PriceCache singleton
    │   ├── simulator.py       # GBMSimulator
    │   └── tapetide.py        # TapetidePoller
    ├── routers/
    │   ├── stream.py          # GET /api/stream/prices  (SSE)
    │   ├── watchlist.py       # CRUD /api/watchlist
    │   ├── portfolio.py       # /api/portfolio and /api/portfolio/trade
    │   └── chat.py            # /api/chat
    └── tests/
        ├── test_simulator.py
        ├── test_cache.py
        └── test_tapetide.py
```

---

## 1. Configuration (`config.py`)

```python
# backend/app/config.py
import os
from pathlib import Path

# Resolved once at import time so every module sees the same value
TAPETIDE_API_KEY: str = os.getenv("TAPETIDE_API_KEY", "").strip()
OPENROUTER_API_KEY: str = os.getenv("OPENROUTER_API_KEY", "").strip()
LLM_MOCK: bool = os.getenv("LLM_MOCK", "false").lower() == "true"

# SQLite file is anchored relative to this file so uvicorn CWD doesn't matter
_HERE = Path(__file__).parent.parent          # backend/
DB_PATH: Path = _HERE.parent / "db" / "finally.db"  # project root /db/finally.db

USE_TAPETIDE: bool = bool(TAPETIDE_API_KEY)
```

---

## 2. Price Entry & Interface (`market/interface.py`)

```python
# backend/app/market/interface.py
from __future__ import annotations
import abc
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PriceEntry:
    ticker: str
    price: float           # latest price (INR)
    prev_price: float      # price before this tick
    change_pct: float      # (price - prev_price) / prev_price * 100
    timestamp: str         # ISO-8601 UTC, e.g. "2026-06-07T09:15:00.123Z"
    direction: str         # "up" | "down" | "flat"

    @classmethod
    def from_prices(cls, ticker: str, price: float, prev_price: float) -> "PriceEntry":
        delta = price - prev_price
        pct = (delta / prev_price * 100) if prev_price else 0.0
        direction = "up" if delta > 0 else ("down" if delta < 0 else "flat")
        return cls(
            ticker=ticker,
            price=round(price, 2),
            prev_price=round(prev_price, 2),
            change_pct=round(pct, 4),
            timestamp=datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.") +
                      f"{datetime.utcnow().microsecond // 1000:03d}Z",
            direction=direction,
        )


class MarketDataInterface(abc.ABC):
    """Both GBMSimulator and TapetidePoller implement this."""

    @abc.abstractmethod
    async def start(self) -> None:
        """Start background polling/simulation. Called once on app startup."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Gracefully shut down. Called on app shutdown."""

    @abc.abstractmethod
    def get_watchlist(self) -> list[str]:
        """Return the current set of tickers being tracked."""

    @abc.abstractmethod
    def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the active tracking set."""

    @abc.abstractmethod
    def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker from the active tracking set."""
```

---

## 3. Price Cache (`market/cache.py`)

The cache is a module-level singleton. All readers and writers share the same
dict. Because Python's GIL ensures dict updates are atomic for simple
assignments, no explicit lock is needed for the read path. Writes from the
background task (single coroutine) are safe without locking.

```python
# backend/app/market/cache.py
from __future__ import annotations
from typing import Optional
from .interface import PriceEntry

# ticker → PriceEntry (latest known state)
_cache: dict[str, PriceEntry] = {}


def update(entry: PriceEntry) -> None:
    """Write a new price entry into the cache."""
    _cache[entry.ticker] = entry


def get(ticker: str) -> Optional[PriceEntry]:
    return _cache.get(ticker)


def get_all() -> dict[str, PriceEntry]:
    """Return a shallow copy so callers don't mutate the live cache."""
    return dict(_cache)


def snapshot_prices() -> list[PriceEntry]:
    """Ordered list of all current prices (for SSE broadcast)."""
    return list(_cache.values())
```

---

## 4. GBM Simulator (`market/simulator.py`)

Uses Geometric Brownian Motion. Each tick advances every ticker by a random
log-return drawn from N(μ·dt, σ·√dt). Occasional random "events" spike a
single ticker by 2–5 %.

### Seed prices (INR, approximate realistic values)

```python
SEED_PRICES: dict[str, float] = {
    "RELIANCE":    2850.0,
    "TCS":         3900.0,
    "INFY":        1750.0,
    "HDFCBANK":    1680.0,
    "ICICIBANK":    950.0,
    "HINDUNILVR":  2700.0,
    "SBIN":         820.0,
    "WIPRO":        480.0,
    "BAJFINANCE":  7200.0,
    "TATAMOTORS":   950.0,
}
```

### Full implementation

```python
# backend/app/market/simulator.py
from __future__ import annotations
import asyncio
import math
import random
from typing import Optional

from .interface import MarketDataInterface, PriceEntry
from . import cache

# Deterministic seed for E2E tests when LLM_MOCK is True
_RNG = random.Random()

SEED_PRICES: dict[str, float] = {
    "RELIANCE":    2850.0,
    "TCS":         3900.0,
    "INFY":        1750.0,
    "HDFCBANK":    1680.0,
    "ICICIBANK":    950.0,
    "HINDUNILVR":  2700.0,
    "SBIN":         820.0,
    "WIPRO":        480.0,
    "BAJFINANCE":  7200.0,
    "TATAMOTORS":   950.0,
}

# GBM parameters
DRIFT     = 0.0          # μ — neutral drift (no trend)
VOLATILITY = 0.015       # σ — ~1.5% annualised per tick, keeps it lively
TICK_INTERVAL = 0.5      # seconds between ticks
EVENT_PROB = 0.005       # probability of a sudden 2-5% event per ticker per tick

# Correlation: tech tickers move slightly together
TECH = {"TCS", "INFY", "WIPRO"}


class GBMSimulator(MarketDataInterface):
    def __init__(self, deterministic: bool = False) -> None:
        self._prices: dict[str, float] = {}
        self._task: Optional[asyncio.Task] = None
        if deterministic:
            _RNG.seed(42)

    # ── MarketDataInterface ──────────────────────────────────────────────────

    async def start(self) -> None:
        self._prices = dict(SEED_PRICES)
        # Seed the cache with initial prices before the first tick
        for ticker, price in self._prices.items():
            cache.update(PriceEntry.from_prices(ticker, price, price))
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def get_watchlist(self) -> list[str]:
        return list(self._prices.keys())

    def add_ticker(self, ticker: str) -> None:
        if ticker not in self._prices:
            # Start new tickers at a neutral ₹1000 until a real price appears
            self._prices[ticker] = 1000.0
            cache.update(PriceEntry.from_prices(ticker, 1000.0, 1000.0))

    def remove_ticker(self, ticker: str) -> None:
        self._prices.pop(ticker, None)

    # ── Internal ─────────────────────────────────────────────────────────────

    async def _run(self) -> None:
        dt = TICK_INTERVAL / (252 * 6.5 * 3600)  # fraction of a trading year
        while True:
            await asyncio.sleep(TICK_INTERVAL)
            # Shared market shock (mild correlation for tech tickers)
            market_shock = _RNG.gauss(0, 1) * 0.3

            for ticker, prev in list(self._prices.items()):
                shock = _RNG.gauss(0, 1)
                if ticker in TECH:
                    shock = shock * 0.7 + market_shock * 0.3

                log_return = (DRIFT - 0.5 * VOLATILITY ** 2) * dt + \
                             VOLATILITY * math.sqrt(dt) * shock

                new_price = prev * math.exp(log_return)

                # Random event: sudden 2-5% move
                if _RNG.random() < EVENT_PROB:
                    spike = _RNG.uniform(0.02, 0.05)
                    new_price *= (1 + spike) if _RNG.random() > 0.5 else (1 - spike)

                new_price = max(new_price, 1.0)  # floor at ₹1
                self._prices[ticker] = new_price
                cache.update(PriceEntry.from_prices(ticker, new_price, prev))
```

---

## 5. Tapetide Poller (`market/tapetide.py`)

### Strategy

- Every **10 seconds**: fetch real prices from Tapetide's `get_batch_quotes` and
  snap the cache to true market values.
- Every **0.5 seconds** between polls: apply low-volatility GBM micro-moves so
  the UI stays alive (flash animations, sparklines keep updating).

### Ticker normalisation

Tapetide expects NSE tickers **without** an `.NS` suffix. Strip any suffix and
upper-case before sending. `M&M` is sent as-is (Tapetide handles it).

```python
def _normalise(ticker: str) -> str:
    """Strip .NS / .BSE suffix; upper-case."""
    return ticker.upper().removesuffix(".NS").removesuffix(".BSE")
```

### Full implementation

```python
# backend/app/market/tapetide.py
from __future__ import annotations
import asyncio
import math
import random
import time
from typing import Optional

import fastmcp

from .interface import MarketDataInterface, PriceEntry
from . import cache

POLL_INTERVAL   = 10.0   # seconds between Tapetide fetches
MICRO_INTERVAL  = 0.5    # seconds between micro-move ticks
MICRO_VOLATILITY = 0.003  # σ for between-poll micro-moves (very low)
MCP_URL = "https://mcp.tapetide.com/mcp"


def _normalise(ticker: str) -> str:
    return ticker.upper().removesuffix(".NS").removesuffix(".BSE")


class TapetidePoller(MarketDataInterface):
    def __init__(self, api_key: str) -> None:
        self._api_key = api_key
        self._tickers: set[str] = set()
        self._micro_prices: dict[str, float] = {}
        self._poll_task:  Optional[asyncio.Task] = None
        self._micro_task: Optional[asyncio.Task] = None

    # ── MarketDataInterface ──────────────────────────────────────────────────

    async def start(self) -> None:
        self._poll_task  = asyncio.create_task(self._poll_loop())
        self._micro_task = asyncio.create_task(self._micro_loop())

    async def stop(self) -> None:
        for task in (self._poll_task, self._micro_task):
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

    def get_watchlist(self) -> list[str]:
        return list(self._tickers)

    def add_ticker(self, ticker: str) -> None:
        self._tickers.add(_normalise(ticker))

    def remove_ticker(self, ticker: str) -> None:
        self._tickers.discard(_normalise(ticker))

    # ── Poll loop (real Tapetide data every 10 s) ────────────────────────────

    async def _poll_loop(self) -> None:
        while True:
            await self._fetch_and_update()
            await asyncio.sleep(POLL_INTERVAL)

    async def _fetch_and_update(self) -> None:
        if not self._tickers:
            return
        tickers = list(self._tickers)
        try:
            async with fastmcp.Client(
                MCP_URL,
                auth=self._api_key,        # Bearer token
            ) as client:
                result = await client.call_tool(
                    "get_batch_quotes",
                    {"symbols": tickers},
                )
            # result is a list of dicts: [{symbol, price, ...}, ...]
            for quote in result:
                ticker = _normalise(quote["symbol"])
                real_price = float(quote["price"])
                prev_entry = cache.get(ticker)
                prev_price = prev_entry.price if prev_entry else real_price
                entry = PriceEntry.from_prices(ticker, real_price, prev_price)
                cache.update(entry)
                self._micro_prices[ticker] = real_price   # anchor micro-moves
        except Exception as exc:
            # Log and continue — micro-moves keep the UI alive
            print(f"[TapetidePoller] poll error: {exc}")

    # ── Micro-move loop (GBM between polls) ──────────────────────────────────

    async def _micro_loop(self) -> None:
        dt = MICRO_INTERVAL / (252 * 6.5 * 3600)
        while True:
            await asyncio.sleep(MICRO_INTERVAL)
            for ticker, prev in list(self._micro_prices.items()):
                log_return = random.gauss(0, MICRO_VOLATILITY * math.sqrt(dt))
                new_price = max(prev * math.exp(log_return), 1.0)
                self._micro_prices[ticker] = new_price
                cache.update(PriceEntry.from_prices(ticker, new_price, prev))
```

### Example Tapetide response (raw tool output)

```json
[
  {"symbol": "RELIANCE", "price": 2847.55, "volume": 1204332, "open": 2831.0},
  {"symbol": "TCS",      "price": 3912.30, "volume":  887120, "open": 3890.0}
]
```

---

## 6. Factory (`market/__init__.py`)

```python
# backend/app/market/__init__.py
from app.config import USE_TAPETIDE, TAPETIDE_API_KEY, LLM_MOCK
from .interface import MarketDataInterface
from .simulator import GBMSimulator
from .tapetide import TapetidePoller


def create_market_data() -> MarketDataInterface:
    if USE_TAPETIDE:
        return TapetidePoller(api_key=TAPETIDE_API_KEY)
    return GBMSimulator(deterministic=LLM_MOCK)
```

---

## 7. App Lifecycle (`main.py`)

```python
# backend/app/main.py  (relevant excerpt)
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.market import create_market_data
from app.database import init_db

market_data = create_market_data()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()                       # create tables + seed data (idempotent)
    watchlist = _load_watchlist()   # read persisted tickers from DB
    for ticker in watchlist:
        market_data.add_ticker(ticker)
    await market_data.start()
    yield
    await market_data.stop()


app = FastAPI(lifespan=lifespan)
```

`_load_watchlist()` queries `SELECT ticker FROM watchlist WHERE user_id='default'`
and returns the list. This seeds the market data layer from DB state so the
simulator/poller tracks the right tickers immediately on startup.

---

## 8. SSE Endpoint (`routers/stream.py`)

### SSE Event Schema

Each event is a JSON object. Field names are fixed — frontend and backend must
both use this exact schema:

```
event: price_update
data: {
  "ticker":      "RELIANCE",       // string, NSE symbol
  "price":       2847.55,          // float, current price INR
  "prev_price":  2843.10,          // float, previous tick price
  "change_pct":  0.1566,           // float, % change this tick
  "direction":   "up",             // "up" | "down" | "flat"
  "timestamp":   "2026-06-07T09:15:00.123Z"  // ISO-8601 UTC
}
```

### Implementation

```python
# backend/app/routers/stream.py
import asyncio
import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.market import cache

router = APIRouter()
BROADCAST_INTERVAL = 0.5   # seconds


@router.get("/api/stream/prices")
async def stream_prices():
    async def event_generator():
        while True:
            entries = cache.snapshot_prices()
            for entry in entries:
                payload = json.dumps({
                    "ticker":     entry.ticker,
                    "price":      entry.price,
                    "prev_price": entry.prev_price,
                    "change_pct": entry.change_pct,
                    "direction":  entry.direction,
                    "timestamp":  entry.timestamp,
                })
                yield f"event: price_update\ndata: {payload}\n\n"
            await asyncio.sleep(BROADCAST_INTERVAL)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable Nginx buffering
        },
    )
```

### Frontend connection (TypeScript reference)

```typescript
const es = new EventSource("/api/stream/prices");
es.addEventListener("price_update", (e) => {
  const data = JSON.parse(e.data) as {
    ticker: string;
    price: number;
    prev_price: number;
    change_pct: number;
    direction: "up" | "down" | "flat";
    timestamp: string;
  };
  // update price cache, trigger flash animation, append to sparkline
});
```

---

## 9. Watchlist Integration

When the watchlist API adds or removes a ticker, it must also notify the active
market data implementation so it starts/stops tracking:

```python
# backend/app/routers/watchlist.py  (relevant excerpt)
from app.main import market_data   # the running singleton

@router.post("/api/watchlist")
async def add_to_watchlist(body: AddTickerRequest, db: sqlite3.Connection = Depends(get_db)):
    ticker = body.ticker.upper().strip()
    # ... insert into DB ...
    market_data.add_ticker(ticker)
    return {"ticker": ticker, "added": True}

@router.delete("/api/watchlist/{ticker}")
async def remove_from_watchlist(ticker: str, db: sqlite3.Connection = Depends(get_db)):
    ticker = ticker.upper()         # URL-decode handled by FastAPI automatically
    # ... delete from DB ...
    market_data.remove_ticker(ticker)
    return {"ticker": ticker, "removed": True}
```

**Note on `M&M`**: FastAPI/Starlette decodes URL-encoded path params automatically.
The frontend must send `DELETE /api/watchlist/M%26M` and the backend receives
`ticker = "M&M"` correctly. No special backend handling needed.

---

## 10. Ticker Normalisation Rules

| Input            | Normalised  | Notes                              |
|------------------|-------------|------------------------------------|
| `reliance`       | `RELIANCE`  | Upper-case only                    |
| `TCS.NS`         | `TCS`       | Strip `.NS` suffix                 |
| `SBIN.BSE`       | `SBIN`      | Strip `.BSE` suffix                |
| `M&M`            | `M&M`       | Ampersand preserved                |
| ` INFY `         | `INFY`      | Strip surrounding whitespace       |

All normalisation is applied at the boundary (API input, Tapetide response).
The cache always stores the normalised form.

---

## 11. Portfolio Snapshot Task

A background coroutine records total portfolio value every 30 seconds.
It is launched alongside the market data task in `lifespan`.

```python
# backend/app/snapshots.py
import asyncio
import sqlite3
import uuid
from datetime import datetime, timezone
from app.market import cache
from app.database import get_db_connection


async def snapshot_loop() -> None:
    while True:
        await asyncio.sleep(30)
        _record_snapshot()
        _prune_old_snapshots()


def _record_snapshot() -> None:
    with get_db_connection() as conn:
        positions = conn.execute(
            "SELECT ticker, quantity, avg_cost FROM positions WHERE user_id='default'"
        ).fetchall()
        cash = conn.execute(
            "SELECT cash_balance FROM users_profile WHERE id='default'"
        ).fetchone()["cash_balance"]

        market_value = sum(
            row["quantity"] * (cache.get(row["ticker"]).price if cache.get(row["ticker"])
                               else row["avg_cost"])
            for row in positions
        )
        total_value = cash + market_value

        conn.execute(
            "INSERT INTO portfolio_snapshots (id, user_id, total_value, recorded_at) "
            "VALUES (?, 'default', ?, ?)",
            (str(uuid.uuid4()), total_value,
             datetime.now(timezone.utc).isoformat()),
        )


def _prune_old_snapshots() -> None:
    """Keep only the last 24 hours of snapshots."""
    with get_db_connection() as conn:
        conn.execute(
            "DELETE FROM portfolio_snapshots WHERE user_id='default' "
            "AND recorded_at < datetime('now', '-24 hours')"
        )
```

`total_value` = cash balance + sum(quantity × current price) for all positions.
This definition is used consistently in both the snapshot task and `GET /api/portfolio`.

---

## 12. Tests

### Simulator unit tests (`tests/test_simulator.py`)

```python
import asyncio
import pytest
from app.market.simulator import GBMSimulator, SEED_PRICES
from app.market import cache


@pytest.fixture()
async def sim():
    s = GBMSimulator(deterministic=True)
    await s.start()
    yield s
    await s.stop()


@pytest.mark.asyncio
async def test_seed_prices_in_cache(sim):
    for ticker in SEED_PRICES:
        entry = cache.get(ticker)
        assert entry is not None
        assert entry.price > 0


@pytest.mark.asyncio
async def test_prices_change_after_tick(sim):
    before = {t: cache.get(t).price for t in SEED_PRICES}
    await asyncio.sleep(0.6)   # one full tick interval
    after  = {t: cache.get(t).price for t in SEED_PRICES}
    # At least some prices should have changed
    assert any(before[t] != after[t] for t in SEED_PRICES)


@pytest.mark.asyncio
async def test_add_remove_ticker(sim):
    sim.add_ticker("NEWCO")
    assert "NEWCO" in sim.get_watchlist()
    sim.remove_ticker("NEWCO")
    assert "NEWCO" not in sim.get_watchlist()


def test_price_entry_direction():
    from app.market.interface import PriceEntry
    e = PriceEntry.from_prices("X", 110.0, 100.0)
    assert e.direction == "up"
    assert round(e.change_pct, 1) == 10.0

    e2 = PriceEntry.from_prices("X", 90.0, 100.0)
    assert e2.direction == "down"
```

### Cache unit tests (`tests/test_cache.py`)

```python
from app.market.interface import PriceEntry
from app.market import cache as price_cache


def test_update_and_get():
    entry = PriceEntry.from_prices("TEST", 500.0, 490.0)
    price_cache.update(entry)
    result = price_cache.get("TEST")
    assert result.ticker == "TEST"
    assert result.price == 500.0
    assert result.direction == "up"


def test_get_all_returns_copy():
    snap = price_cache.get_all()
    snap["FAKE"] = None          # mutating the copy
    assert price_cache.get("FAKE") is None   # original unchanged


def test_missing_ticker_returns_none():
    assert price_cache.get("DOESNOTEXIST") is None
```

### Tapetide poller tests (`tests/test_tapetide.py`)

These tests mock the `fastmcp.Client` to avoid network calls.

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.market.tapetide import TapetidePoller
from app.market import cache


MOCK_QUOTES = [
    {"symbol": "RELIANCE", "price": 2900.0},
    {"symbol": "TCS",      "price": 4000.0},
]


@pytest.fixture()
def poller():
    p = TapetidePoller(api_key="test-key")
    p.add_ticker("RELIANCE")
    p.add_ticker("TCS")
    return p


@pytest.mark.asyncio
async def test_fetch_updates_cache(poller):
    mock_client = AsyncMock()
    mock_client.call_tool = AsyncMock(return_value=MOCK_QUOTES)
    mock_ctx = AsyncMock(__aenter__=AsyncMock(return_value=mock_client),
                         __aexit__=AsyncMock(return_value=False))

    with patch("app.market.tapetide.fastmcp.Client", return_value=mock_ctx):
        await poller._fetch_and_update()

    assert cache.get("RELIANCE").price == 2900.0
    assert cache.get("TCS").price == 4000.0


@pytest.mark.asyncio
async def test_poll_error_does_not_crash(poller):
    mock_ctx = AsyncMock(__aenter__=AsyncMock(side_effect=ConnectionError("network")),
                         __aexit__=AsyncMock(return_value=False))
    with patch("app.market.tapetide.fastmcp.Client", return_value=mock_ctx):
        # Should not raise
        await poller._fetch_and_update()


def test_normalise():
    from app.market.tapetide import _normalise
    assert _normalise("tcs.NS") == "TCS"
    assert _normalise("SBIN.BSE") == "SBIN"
    assert _normalise("M&M") == "M&M"
    assert _normalise(" reliance ") == "RELIANCE"   # after .strip() at boundary
```

---

## 13. `pyproject.toml` (key dependencies)

```toml
[project]
name = "finally-backend"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.29",
    "fastmcp>=0.9",           # Tapetide MCP client
    "litellm>=1.40",          # LLM via OpenRouter
    "pytest>=8",
    "pytest-asyncio>=0.23",
]
```

---

## 14. Environment Variable Summary

| Variable           | Required | Default | Effect                                             |
|--------------------|----------|---------|----------------------------------------------------|
| `TAPETIDE_API_KEY` | No       | `""`    | Non-empty → TapetidePoller; empty → GBMSimulator   |
| `OPENROUTER_API_KEY` | Yes    | —       | LLM chat via OpenRouter / Cerebras                 |
| `LLM_MOCK`         | No       | `false` | `true` → deterministic simulator seed + mock LLM  |

---

## 15. Key Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| Abstract `MarketDataInterface` | Downstream code (SSE, watchlist) never imports simulator or Tapetide directly — swapping is one line in the factory |
| In-memory price cache (no DB) | Sub-millisecond reads for SSE broadcast; acceptable loss on restart (prices re-anchor within 10 s) |
| GBM micro-moves in TapetidePoller | Tapetide polls every 10 s; micro-moves keep the UI lively between polls without fake volatility compounding |
| `deterministic=True` in GBMSimulator | E2E tests get reproducible price sequences; seeded with `random.Random(42)` |
| `PriceEntry.from_prices` factory | Direction and `change_pct` are always computed consistently — no drift between implementations |
| WAL mode for SQLite | Background snapshot task + concurrent API writes need WAL to avoid `database is locked` |
| Ticker normalisation at boundary | Single point of truth; cache always stores clean NSE symbols |
