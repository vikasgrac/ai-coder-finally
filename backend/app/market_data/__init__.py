"""
Market data package.

Factory function selects between:
  - TapetidePoller  — when TAPETIDE_API_KEY is set (live NSE/BSE data)
  - MarketSimulator — default (GBM-based simulator, no external deps)
"""
import os

from app.market_data.interface import MarketDataInterface, PriceData
from app.market_data.simulator import MarketSimulator
from app.market_data.tapetide import TapetidePoller

__all__ = [
    "MarketDataInterface",
    "PriceData",
    "MarketSimulator",
    "TapetidePoller",
    "create_market_data_provider",
]


def create_market_data_provider() -> MarketDataInterface:
    """Return the appropriate provider based on available environment variables."""
    api_key = os.getenv("TAPETIDE_API_KEY", "").strip()
    if api_key:
        return TapetidePoller(api_key=api_key)
    return MarketSimulator()
