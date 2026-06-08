"""
Tapetide market data provider for live NSE/BSE prices via FastMCP.

Architecture:
  - Every POLL_INTERVAL seconds, fetch real prices from Tapetide MCP server
  - Between polls, apply low-volatility GBM micro-moves so the UI stays fluid
  - On each Tapetide poll the cache snaps to real market values; micro-moves
    resume from there

Environment variable: TAPETIDE_API_KEY (Bearer token)
MCP endpoint:         https://mcp.tapetide.com/mcp
"""
import asyncio
import json
import logging
import math
import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set

from app.market_data.interface import MarketDataInterface, PriceData
from app.market_data.simulator import DEFAULT_SEED_PRICE, SEED_PRICES

logger = logging.getLogger(__name__)

# fastmcp is an optional runtime dependency; import lazily so that importing
# this module never raises ImportError when fastmcp is absent (e.g. in tests).
try:
    import fastmcp as _fastmcp_module
    _HAS_FASTMCP = True
except ImportError:
    _fastmcp_module = None  # type: ignore[assignment]
    _HAS_FASTMCP = False


class TapetidePoller(MarketDataInterface):
    """
    Live NSE/BSE prices from Tapetide via FastMCP HTTP transport.

    Real-price poll: every POLL_INTERVAL seconds
    GBM micro-moves: every MICRO_INTERVAL seconds (low volatility)
    """

    POLL_INTERVAL:    float = 10.0
    MICRO_INTERVAL:   float = 0.5
    MICRO_VOLATILITY: float = 0.0005

    DEFAULT_MCP_URL = "https://mcp.tapetide.com/mcp"

    def __init__(
        self,
        api_key: str,
        mcp_url: str = DEFAULT_MCP_URL,
    ) -> None:
        super().__init__()
        self._api_key  = api_key
        self._mcp_url  = mcp_url
        self._tickers: Set[str] = set()
        self._poll_task:  Optional[asyncio.Task] = None  # type: ignore[type-arg]
        self._micro_task: Optional[asyncio.Task] = None  # type: ignore[type-arg]

    # ------------------------------------------------------------------
    # MarketDataInterface implementation
    # ------------------------------------------------------------------

    async def start(self, tickers: List[str]) -> None:
        for ticker in tickers:
            await self.add_ticker(ticker)
        self._running = True
        # Seed the cache with real prices immediately before starting loops
        await self._poll_tapetide()
        self._poll_task  = asyncio.create_task(self._poll_loop())
        self._micro_task = asyncio.create_task(self._micro_loop())

    async def stop(self) -> None:
        self._running = False
        for task in (self._poll_task, self._micro_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._poll_task  = None
        self._micro_task = None

    async def add_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            return
        self._tickers.add(ticker)
        now = datetime.now(timezone.utc).isoformat()
        # Seed from known INR prices so micro-moves can start immediately;
        # the first real Tapetide poll will snap to the live market value.
        seed = SEED_PRICES.get(ticker, DEFAULT_SEED_PRICE)
        self._price_cache[ticker] = PriceData(
            ticker=ticker,
            price=seed,
            previous_price=seed,
            timestamp=now,
            change_direction="unchanged",
        )

    async def remove_ticker(self, ticker: str) -> None:
        self._tickers.discard(ticker)
        self._price_cache.pop(ticker, None)

    # ------------------------------------------------------------------
    # Internal polling loops
    # ------------------------------------------------------------------

    async def _poll_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.POLL_INTERVAL)
            if self._tickers:
                await self._poll_tapetide()

    async def _micro_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.MICRO_INTERVAL)
            self._apply_micro_moves()

    # ------------------------------------------------------------------
    # Tapetide MCP call
    # ------------------------------------------------------------------

    async def _poll_tapetide(self) -> None:
        if not self._tickers:
            return
        if not _HAS_FASTMCP:
            logger.error("fastmcp is not installed; cannot poll Tapetide")
            return

        try:
            async with _fastmcp_module.Client(
                self._mcp_url, auth=self._api_key
            ) as client:
                tickers_list = list(self._tickers)
                result = await client.call_tool(
                    "get_batch_quotes",
                    {"symbols": tickers_list},
                )
                self._process_quotes(result)
        except Exception as exc:  # network errors, auth failures, etc.
            logger.error("TapetidePoller poll failed: %s", exc)

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _process_quotes(self, result: Any) -> None:
        """
        Parse the raw FastMCP call result and update the price cache.

        FastMCP v2 returns a CallToolResult with a .content list of TextContent
        items.  Each TextContent.text may contain JSON with one of several shapes:
          - {"data": [{"symbol": …, "price": …}, …], "meta": {…}}   (Tapetide)
          - list of {"ticker"/"symbol": …, "price"/"last_price"/"ltp": …}
          - dict mapping ticker → {"price"/"last_price"/"ltp": …}
          - dict mapping ticker → scalar price
        """
        if not result:
            return

        now = datetime.now(timezone.utc).isoformat()

        # --- unwrap CallToolResult (fastmcp v2 wraps results in this object) ---
        content_items = getattr(result, "content", None)
        if content_items is not None:
            result = content_items  # treat the .content list as the raw result

        # --- unwrap list of TextContent items ---
        raw: Any = result
        if isinstance(result, list):
            had_text_content = False
            for item in result:
                text = getattr(item, "text", None)
                if text:
                    had_text_content = True
                    try:
                        raw = json.loads(text)
                        break
                    except (json.JSONDecodeError, TypeError):
                        continue
            else:
                # for-else: loop completed without break (no valid JSON found)
                if had_text_content:
                    logger.error(
                        "TapetidePoller: all TextContent items contained invalid JSON;"
                        " price cache not updated"
                    )
                    return
                elif result and not hasattr(result[0], "text"):
                    # plain Python list (e.g. from tests)
                    raw = result

        # --- unwrap Tapetide envelope {"data": [...], "meta": {...}} ---
        if isinstance(raw, dict) and "data" in raw and isinstance(raw["data"], list):
            raw = raw["data"]

        # --- dispatch on shape ---
        if isinstance(raw, list):
            for item in raw:
                if isinstance(item, dict):
                    self._update_from_quote(item, now)
        elif isinstance(raw, dict):
            for ticker, data in raw.items():
                if isinstance(data, dict):
                    self._update_from_quote_dict(ticker, data, now)
                elif isinstance(data, (int, float)):
                    # {"RELIANCE": 1320.5, ...}
                    self._set_price(ticker, float(data), now)

    def _update_from_quote(self, quote: Dict[str, Any], now: str) -> None:
        """Handle a single quote dict that includes the ticker key."""
        ticker = quote.get("ticker") or quote.get("symbol")
        # Use `k in quote` rather than truthiness so price=0.0 is not skipped
        price = next(
            (quote[k] for k in ("price", "last_price", "ltp") if k in quote),
            None,
        )
        if ticker and price is not None:
            self._set_price(str(ticker), float(price), now)

    def _update_from_quote_dict(
        self, ticker: str, data: Dict[str, Any], now: str
    ) -> None:
        """Handle a quote nested under the ticker key."""
        # Use `k in data` rather than truthiness so price=0.0 is not skipped
        price = next(
            (data[k] for k in ("price", "last_price", "ltp") if k in data),
            None,
        )
        if price is not None:
            self._set_price(ticker, float(price), now)

    def _set_price(self, ticker: str, new_price: float, now: str) -> None:
        if ticker not in self._tickers:
            return
        current   = self._price_cache.get(ticker)
        old_price = current.price if current else new_price
        direction = (
            "up"        if new_price > old_price else
            "down"      if new_price < old_price else
            "unchanged"
        )
        self._price_cache[ticker] = PriceData(
            ticker=ticker,
            price=round(new_price, 2),
            previous_price=round(old_price, 2),
            timestamp=now,
            change_direction=direction,
        )

    # ------------------------------------------------------------------
    # GBM micro-moves (between real polls)
    # ------------------------------------------------------------------

    def _apply_micro_moves(self) -> None:
        """Apply tiny GBM perturbations to all prices to keep the UI lively."""
        now = datetime.now(timezone.utc).isoformat()
        dt  = self.MICRO_INTERVAL
        sigma = self.MICRO_VOLATILITY

        for ticker in list(self._tickers):
            if ticker not in self._price_cache:
                continue
            current = self._price_cache[ticker]
            if current.price <= 0:
                continue  # not yet seeded from a real poll

            old_price = current.price
            z         = random.gauss(0, 1)
            log_ret   = (-0.5 * sigma ** 2 * dt) + (sigma * math.sqrt(dt) * z)
            new_price = max(round(old_price * math.exp(log_ret), 2), 0.01)

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
