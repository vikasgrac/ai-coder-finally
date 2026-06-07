"""
GBM-based market data simulator for NSE/BSE tickers.

Generates realistic INR prices using Geometric Brownian Motion with:
  - Correlated moves within sector groups (IT, Banking, etc.)
  - Occasional random "events" mimicking news/volatility spikes
  - ~500 ms update cadence (configurable)
"""
import asyncio
import math
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from app.market_data.interface import MarketDataInterface, PriceData

# Approximate INR seed prices for default NSE watchlist
SEED_PRICES: Dict[str, float] = {
    "RELIANCE":    1300.0,
    "TCS":         2200.0,
    "INFY":        1200.0,
    "HDFCBANK":    1600.0,
    "ICICIBANK":    900.0,
    "HINDUNILVR":  2500.0,
    "SBIN":         600.0,
    "WIPRO":        450.0,
    "BAJFINANCE":  7000.0,
    "TATAMOTORS":   500.0,
}

DEFAULT_SEED_PRICE = 1000.0

# Sector correlation groups — tickers in the same list share a common shock
CORRELATION_GROUPS: List[List[str]] = [
    ["TCS", "INFY", "WIPRO"],                          # IT
    ["HDFCBANK", "ICICIBANK", "SBIN", "BAJFINANCE"],   # Banking / Finance
    ["RELIANCE"],                                        # Conglomerate
    ["HINDUNILVR"],                                      # FMCG
    ["TATAMOTORS"],                                      # Auto
]


class MarketSimulator(MarketDataInterface):
    """
    In-process market simulator that uses GBM to drive synthetic prices.

    GBM step:
        S(t+dt) = S(t) * exp( (μ − σ²/2)·dt  +  σ·√dt·Z )

    where Z is a blended shock: 50% sector-level + 50% idiosyncratic,
    normalised so the combined variance is unchanged.
    """

    def __init__(
        self,
        update_interval: float = 0.5,
        drift: float = 0.0001,
        volatility: float = 0.002,
        event_probability: float = 0.005,
        event_max_magnitude: float = 0.05,
    ) -> None:
        super().__init__()
        self._update_interval = update_interval
        self._drift = drift
        self._volatility = volatility
        self._event_probability = event_probability
        self._event_max_magnitude = event_max_magnitude
        self._tickers: Set[str] = set()
        self._task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # MarketDataInterface implementation
    # ------------------------------------------------------------------

    async def start(self, tickers: List[str]) -> None:
        for ticker in tickers:
            await self.add_ticker(ticker)
        self._running = True
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._running = False
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            return
        self._tickers.add(ticker)
        seed = SEED_PRICES.get(ticker, DEFAULT_SEED_PRICE)
        # Small randomisation so not all instances start identically
        initial = seed * (1.0 + random.gauss(0, 0.005))
        now = datetime.now(timezone.utc).isoformat()
        self._price_cache[ticker] = PriceData(
            ticker=ticker,
            price=round(initial, 2),
            previous_price=round(initial, 2),
            timestamp=now,
            change_direction="unchanged",
        )

    async def remove_ticker(self, ticker: str) -> None:
        self._tickers.discard(ticker)
        self._price_cache.pop(ticker, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        while self._running:
            await asyncio.sleep(self._update_interval)
            self._step()

    def _step(self) -> None:
        """Advance all tracked tickers by one GBM step."""
        now = datetime.now(timezone.utc).isoformat()
        dt = self._update_interval

        # Pre-compute one sector shock per group
        group_shocks: Dict[int, float] = {
            i: random.gauss(0, 1) for i in range(len(CORRELATION_GROUPS))
        }

        for ticker in list(self._tickers):
            if ticker not in self._price_cache:
                continue

            old_price = self._price_cache[ticker].price

            # Blend sector shock with idiosyncratic shock
            sector_z = self._sector_shock(ticker, group_shocks)
            idio_z   = random.gauss(0, 1)
            # Equal-weight blend, re-normalised: sqrt(0.5² + 0.5²) = 1/√2
            z = (sector_z + idio_z) / math.sqrt(2)

            log_ret = (
                (self._drift - 0.5 * self._volatility ** 2) * dt
                + self._volatility * math.sqrt(dt) * z
            )
            new_price = old_price * math.exp(log_ret)

            # Occasional news / volatility event
            if random.random() < self._event_probability:
                sign = 1 if random.random() > 0.5 else -1
                mag  = random.uniform(0.02, self._event_max_magnitude)
                new_price *= 1.0 + sign * mag

            new_price = max(round(new_price, 2), 0.01)  # floor at ₹0.01

            direction = (
                "up"        if new_price > old_price else
                "down"      if new_price < old_price else
                "unchanged"
            )

            self._price_cache[ticker] = PriceData(
                ticker=ticker,
                price=new_price,
                previous_price=round(old_price, 2),
                timestamp=now,
                change_direction=direction,
            )

    def _sector_shock(
        self, ticker: str, group_shocks: Dict[int, float]
    ) -> float:
        """Return the pre-computed sector-level shock for *ticker*."""
        for i, group in enumerate(CORRELATION_GROUPS):
            if ticker in group:
                return group_shocks.get(i, 0.0)
        # Unknown ticker: pure idiosyncratic
        return random.gauss(0, 1)
