"""Abstract base class and shared types for market data providers."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class PriceData:
    """A single price snapshot for one ticker."""
    ticker: str
    price: float
    previous_price: float
    timestamp: str          # ISO-8601 UTC
    change_direction: str   # "up" | "down" | "unchanged"


class MarketDataInterface(ABC):
    """
    Abstract interface for market data providers.

    Concrete implementations (MarketSimulator, TapetidePoller) write
    price updates into _price_cache.  All downstream code (SSE stream,
    portfolio P&L) reads from get_price / get_all_prices only.
    """

    def __init__(self) -> None:
        self._price_cache: Dict[str, PriceData] = {}
        self._running: bool = False

    # ------------------------------------------------------------------
    # Abstract contract
    # ------------------------------------------------------------------

    @abstractmethod
    async def start(self, tickers: List[str]) -> None:
        """Start the data source and begin writing to the price cache."""

    @abstractmethod
    async def stop(self) -> None:
        """Stop the data source gracefully."""

    @abstractmethod
    async def add_ticker(self, ticker: str) -> None:
        """Add a ticker to the active tracking set."""

    @abstractmethod
    async def remove_ticker(self, ticker: str) -> None:
        """Remove a ticker from the active tracking set."""

    # ------------------------------------------------------------------
    # Shared read-only accessors (not overridden by subclasses)
    # ------------------------------------------------------------------

    def get_price(self, ticker: str) -> Optional[PriceData]:
        """Return the latest PriceData for *ticker*, or None if unknown."""
        return self._price_cache.get(ticker)

    def get_all_prices(self) -> Dict[str, PriceData]:
        """Return a snapshot of the full price cache."""
        return dict(self._price_cache)

    @property
    def is_running(self) -> bool:
        return self._running
