# FinAlly Project - the Finance Ally

All project documentation is in the `planning` directory.

The key document is PLAN.md included in full below; the market data component has been completed and is summarized in the file `planning/MARKET_DATA_SUMMARY.md` with more details in the `planning/archive` folder. Consult these docs only when required. The remainder of the platform is still to be developed.

@planning/PLAN.md

## Indian Market Data — Tapetide via FastMCP

The PLAN.md describes using the Massive API (Polygon.io) for real market data, but Massive only covers US markets. Since this project targets Indian stocks (NSE/BSE), we use **Tapetide** as the market data source instead.

### Why Tapetide + FastMCP

- Tapetide covers ~8,200 NSE/BSE stocks with live quotes, financials, and more
- Tapetide exposes an MCP server at `https://mcp.tapetide.com/mcp` (HTTP transport)
- The Python backend connects to it as an MCP **client** using `fastmcp` — no REST API wrapper needed
- Verified working: `fastmcp.Client` with Bearer token auth successfully calls `get_batch_quotes` for NSE symbols

### Implementation Plan

Create a `TapetidePoller` class that implements the same `MarketDataInterface` as the existing simulator:
- On startup, connect to `https://mcp.tapetide.com/mcp` using `fastmcp.Client` with `auth=TAPETIDE_API_KEY`
- Poll `get_batch_quotes` with the current watchlist tickers every N seconds
- Write results into the shared in-memory price cache
- All downstream code (SSE stream, portfolio P&L) remains unchanged

### Environment Variable

`TAPETIDE_API_KEY` — set in `.env`. When present and non-empty, backend uses `TapetidePoller`; otherwise falls back to the built-in simulator.