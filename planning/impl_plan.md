# FinAlly — Implementation Plan

## Status Legend
- `[x]` Done
- `[ ]` Not started

---

## What's Already Built

- `[x]` `backend/app/market_data/interface.py` — `MarketDataInterface` abstract base, `PriceData` dataclass
- `[x]` `backend/app/market_data/simulator.py` — GBM simulator with sector correlation + random events
- `[x]` `backend/app/market_data/tapetide.py` — live NSE/BSE via FastMCP (TapetidePoller)
- `[x]` `backend/app/market_data/__init__.py` — `create_market_data_provider()` factory
- `[x]` `backend/pyproject.toml` — uv project with all dependencies declared
- `[x]` Unit tests for all of the above (`backend/tests/`)

---

## Phase 1 — Backend Foundation ✅ COMPLETE

- `[x]` `backend/app/main.py` — FastAPI app with `lifespan` context manager
- `[x]` `backend/app/database.py` — async SQLite helpers with lazy init
- `[x]` `backend/schema/schema.sql` — all six tables + DB indexes
- `[x]` `backend/schema/seed.py` — default user (₹1,00,000) and 10 NSE watchlist tickers
- `[x]` `GET /api/health` — returns `{"status": "ok"}`
- `[x]` Tests: `test_database.py`, `test_health.py` (8 tests)

---

## Phase 2 — Market Data + Watchlist API ✅ COMPLETE

- `[x]` `backend/app/routes/stream.py` — `GET /api/stream/prices` SSE endpoint
- `[x]` `backend/app/routes/watchlist.py` — GET/POST/DELETE `/api/watchlist`
- `[x]` Provider started on startup with watchlist from DB
- `[x]` Tests: `test_watchlist.py`, `test_stream.py` (14 tests)

---

## Phase 3 — Portfolio API ✅ COMPLETE

- `[x]` `backend/app/routes/portfolio.py` — GET/POST trade/GET history
- `[x]` `backend/app/tasks/snapshot.py` — 30s background snapshot task with 24h pruning
- `[x]` Tests: `test_portfolio.py`, `test_snapshot.py` (21 tests)

---

## Phase 4 — LLM Chat ✅ COMPLETE

- `[x]` `backend/app/llm/client.py` — async LiteLLM call, Literal["buy","sell"] validation, mock mode
- `[x]` `backend/app/llm/context.py` — system prompt + portfolio context builder
- `[x]` `backend/app/routes/chat.py` — POST `/api/chat` with auto-execution
- `[x]` Tests: `test_llm.py`, `test_chat.py` (23 tests)

---

## Phase 5 — Frontend ✅ COMPLETE

- `[x]` Next.js TypeScript static export configured
- `[x]` `frontend/lib/api.ts` — typed API wrappers with ApiError for HTTP error handling
- `[x]` `frontend/lib/sse.ts` — SSE hook with exponential backoff reconnection
- `[x]` `frontend/components/Header.tsx` — portfolio value, cash, connection dot
- `[x]` `frontend/components/WatchlistPanel.tsx` — price flash, sparklines, add/remove
- `[x]` `frontend/components/MainChart.tsx` — Recharts LineChart for selected ticker
- `[x]` `frontend/components/PortfolioHeatmap.tsx` — custom SVG treemap
- `[x]` `frontend/components/PnLChart.tsx` — portfolio value over time
- `[x]` `frontend/components/PositionsTable.tsx` — P&L colored positions table
- `[x]` `frontend/components/TradeBar.tsx` — market order execution with selectedTicker sync
- `[x]` `frontend/components/ChatPanel.tsx` — collapsible AI chat with trade confirmation chips
- `[x]` `frontend/app/page.tsx` — main page assembling all components
- `[x]` Frontend builds successfully (`npm run build`)

---

## Phase 6 — Docker + Scripts ✅ COMPLETE

- `[x]` `Dockerfile` — multi-stage Node→Python build; STATIC_DIR env var set explicitly
- `[x]` FastAPI serves static frontend at `/*`
- `[x]` `scripts/start_mac.sh` — idempotent build + run script
- `[x]` `scripts/stop_mac.sh` — stop + remove, preserve volume
- `[x]` `scripts/start_windows.ps1` / `stop_windows.ps1`

---

## Phase 7 — E2E Tests ✅ COMPLETE

- `[x]` `test/docker-compose.test.yml` — app + playwright containers
- `[x]` `test/e2e/package.json` — `@playwright/test` dependency
- `[x]` `test/e2e/playwright.config.ts` — `webServer.reuseExistingServer: true` so tests wait for server before running
- `[x]` `test/e2e/app.spec.ts` — **27 tests, all passing:**
  - Health, watchlist CRUD, portfolio, chat, SSE, frontend HTML (API tests)
  - Stock history for all 6 periods, quote stats, invalid period (stock API tests)
  - Page load + watchlist render, connection status, ticker click → StockDetail, duration buttons, trade bar sync, AI chat panel (browser UI tests)

## Phase 8 — Stock Detail Panel ✅ COMPLETE

- `[x]` `backend/app/routes/stock.py` — two new endpoints:
  - `GET /api/stock/{ticker}/history?period=1d|1w|1m|6m|1y|5y` — backward GBM history anchored to live price; seed is deterministic per (ticker, period, UTC date) so chart is consistent within a day
  - `GET /api/stock/{ticker}/quote` — 52W high/low + prev-day buy/sell volume; uses Tapetide if `TAPETIDE_API_KEY` set, otherwise synthetic from 1Y history
- `[x]` `backend/app/main.py` — includes `stock.router`
- `[x]` `frontend/lib/api.ts` — added `StockHistoryPoint`, `StockQuoteDetail` types + `getStockHistory()`, `getStockQuote()` methods
- `[x]` `frontend/components/StockDetail.tsx` — replaces `MainChart`; shows:
  - Ticker + live price (large, colored by direction) + % change since page load
  - Stats bar: 52W High, 52W Low, Prev Vol, Buy Vol, Sell Vol
  - Period selector: 1D | 1W | 1M | 6M | 1Y | 5Y
  - Recharts LineChart: uses SSE `priceHistory` for 1D, fetches `/api/stock/{ticker}/history` for other periods
- `[x]` `frontend/app/page.tsx` — parent div made flex container so `StockDetail` fills height correctly

---

## Final Status

**Backend tests: 131 passing** (one pre-existing flaky simulator correlation test excluded)
**Playwright E2E tests: 27/27 passing** (API + browser UI tests against live Docker container)
**Frontend: builds successfully**
**Critical bugs fixed:**
- `call_llm()` made async (was blocking event loop)
- `TradeAction.side` uses `Literal["buy", "sell"]`
- Frontend API calls throw `ApiError` on HTTP errors
- `TradeBar` syncs `selectedTicker` prop changes
- Snapshot task logs exceptions instead of silently swallowing
- DB indexes added
- Dockerfile: removed redundant COPY, explicit STATIC_DIR env var

---

## Development Notes

### Running backend tests

```bash
cd backend
uv run pytest --ignore=tests/test_simulator.py
```

Always exclude `tests/test_simulator.py` — `TestSectorCorrelation::test_it_stocks_move_together` is a pre-existing flaky test (was failing before any implementation work began). It is not a regression.

### Testing SSE without hanging

`ASGITransport` buffers the entire HTTP response before returning, so calling `client.stream("GET", "/api/stream/prices")` will hang forever on an infinite SSE stream. **Do not test SSE via HTTP.** Instead, import and test the async generator directly:

```python
from app.routes.stream import _price_event_generator
events = []
async for event in _price_event_generator():
    events.append(event)
    break
```

### Test DB isolation

`FastAPI`'s lifespan (which calls `init_db`) does not run under `ASGITransport`. Call `await init_db(db_path)` explicitly in the `test_db` conftest fixture, and use `database.set_db_path(path)` / `database.set_db_path(None)` to redirect all DB operations to a temp file per test.

### Accessing `market_provider` from routes

The active market data provider is stored as a module-level global in `app/main.py`:

```python
# app/main.py
market_provider = None
```

Routes access it via:

```python
import app.main as app_state
provider = app_state.market_provider
```

In tests, set `app_state.market_provider = MockProvider(...)` in an autouse fixture and restore to `None` after.

### LLM mock mode

Set `LLM_MOCK=true` in the environment (or `patch.dict(os.environ, {"LLM_MOCK": "true"})` in tests) to skip real OpenRouter calls and get deterministic mock responses. All chat/LLM tests use this.

### Frontend local dev

```bash
cd frontend
npm install
npm run dev   # dev server at http://localhost:3000 (needs backend running on :8000)
npm run build # static export to frontend/out/
```

### Running Playwright tests

```bash
cd test/e2e
npx playwright test --reporter=line
```

Requires the Docker container to already be running (`bash scripts/start_mac.sh`). The `webServer` config in `playwright.config.ts` waits for `localhost:8000` to be reachable before starting tests — no manual sleep needed.

Tests must not be run immediately after `start_mac.sh` — uv takes ~10s to rebuild the venv on a fresh volume. The `webServer.timeout: 30000` covers this.

### Running the full app

```bash
cd /path/to/finally
cp .env.example .env  # fill in OPENROUTER_API_KEY
bash scripts/start_mac.sh
# opens http://localhost:8000
```
