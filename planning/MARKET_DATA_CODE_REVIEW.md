# Market Data Backend — Code Review

**Reviewer**: Claude Code (claude-sonnet-4-6)  
**Date**: 2026-06-07  
**Commit reviewed**: `6a2b36e` (Remove lazy imports for massive package — the final implementation state before the backend was reset in `0913790`)  
**Scope**: `backend/app/market/` (8 modules, ~350 SLOC) + `backend/tests/market/` (73 tests)

---

## Test Run Results

```
73 passed, 73 warnings in 1.23s
```

**All 73 tests pass.** Lint (`ruff`) is also clean.

> **Important caveat**: `uv run pytest` fails with `ModuleNotFoundError: No module named 'massive'` because `uv run` picks up the globally-installed pytest binary (not the venv's). Tests only pass with `.venv/bin/pytest`. This is a developer-experience bug — anyone following the standard `uv run pytest` workflow will see 5 collection errors.

### Coverage Summary

| Module | Coverage | Uncovered lines |
|---|---|---|
| `models.py` | **100%** | — |
| `cache.py` | **100%** | — |
| `interface.py` | **100%** | — |
| `seed_prices.py` | **100%** | — |
| `factory.py` | **100%** | — |
| `massive_client.py` | **94%** | 85-87 (`_poll_loop` body), 125 (`_fetch_snapshots` sync call) |
| `simulator.py` | **98%** | 149 (duplicate ticker guard), 268-269 (exception log) |
| `stream.py` | **33%** | 26-48 (route handler), 62-87 (event generator) |
| **Total** | **91%** | |

The low `stream.py` coverage is expected (requires a running ASGI server), but the module has **zero functional tests** — neither the SSE response headers nor the generator behaviour are tested at all.

---

## Findings

Findings are ranked: **Critical** (blocks the next phase) → **Bug** (wrong at runtime) → **Design** (technical debt) → **Test gap**.

---

### CRITICAL — Specification Mismatches (Must Fix Before Next Phase)

#### C1 — Wrong environment variable in factory (`factory.py:13`)

```python
api_key = os.environ.get("MASSIVE_API_KEY", "").strip()
```

The project spec and `.env.example` define `TAPETIDE_API_KEY` as the environment variable for live market data. `MASSIVE_API_KEY` is the old Polygon.io variable. With the current code, setting `TAPETIDE_API_KEY` has **no effect** — the factory always falls through to the simulator, silently ignoring the configured API key.

**Fix**: Change to `os.environ.get("TAPETIDE_API_KEY", "")`.

---

#### C2 — Wrong live data implementation (`massive_client.py`, `factory.py`)

`MassiveDataSource` uses the Polygon.io REST API (`RESTClient.get_snapshot_all`) which:
- Only covers **US stocks** (not NSE/BSE)
- Uses a synchronous REST client that blocks the event loop (mitigated by `asyncio.to_thread`, but still)
- Is not compatible with the Tapetide MCP endpoint

The spec requires a `TapetidePoller` class that:
- Connects to `https://mcp.tapetide.com/mcp` using `fastmcp.Client` with Bearer token auth
- Calls the `get_batch_quotes` MCP tool every ~10 seconds
- Applies low-volatility GBM micro-moves between polls (the hybrid approach)

`MassiveDataSource` cannot be adapted for this — it needs to be **replaced** with a new `TapetidePoller` class. The abstract `MarketDataSource` interface and `PriceCache` remain valid.

---

#### C3 — US tickers and USD prices in simulator seed data (`seed_prices.py`)

```python
SEED_PRICES = {
    "AAPL": 190.00, "GOOGL": 175.00, "MSFT": 420.00, ...
}
CORRELATION_GROUPS = {
    "tech": {"AAPL", "GOOGL", "MSFT", "AMZN", "META", "NVDA", "NFLX"},
    "finance": {"JPM", "V"},
}
```

The spec's default watchlist is **NSE tickers** (RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, HINDUNILVR, SBIN, WIPRO, BAJFINANCE, TATAMOTORS) at **INR prices** (e.g., RELIANCE ~₹1300, TCS ~₹2200). The SQLite seed data inserts these NSE tickers, but the simulator has no seed prices for them — they fall through to `random.uniform(50.0, 300.0)`, producing nonsensical ₹50–300 prices and no meaningful correlation structure.

**Fix**: Replace `SEED_PRICES`, `TICKER_PARAMS`, and `CORRELATION_GROUPS` with Indian market data. Suggested seed values:

| Ticker | Approx. INR price | Sector |
|---|---|---|
| RELIANCE | 1,300 | energy/conglomerate |
| TCS | 2,200 | IT services |
| INFY | 1,200 | IT services |
| HDFCBANK | 1,650 | private banks |
| ICICIBANK | 1,200 | private banks |
| HINDUNILVR | 2,400 | FMCG |
| SBIN | 800 | PSU banks |
| WIPRO | 280 | IT services |
| BAJFINANCE | 7,000 | NBFCs |
| TATAMOTORS | 950 | auto |

Suggested correlation groups: `"it"` (TCS, INFY, WIPRO), `"pvt_banks"` (HDFCBANK, ICICIBANK), `"conglomerate"` (RELIANCE, TATAMOTORS), `"fmcg"` (HINDUNILVR), `"finance"` (BAJFINANCE, SBIN).

---

### BUG — Correctness Issues

#### B1 — `timestamp=0.0` overwritten by `time.time()` (`cache.py:18`)

```python
ts = timestamp or time.time()
```

`timestamp` is typed `float | None`. A legitimate `timestamp=0.0` (Unix epoch, used in some tests and edge cases) evaluates as falsy and gets silently replaced with the current time. This can cause `test_timestamp_conversion` to pass with the wrong value in certain timing scenarios.

**Fix**: `ts = timestamp if timestamp is not None else time.time()`

---

#### B2 — Cholesky can raise unhandled `LinAlgError` (`simulator.py:160`)

```python
self._cholesky = np.linalg.cholesky(corr)
```

`np.linalg.cholesky` raises `numpy.linalg.LinAlgError` if the matrix is not strictly positive definite. This call is inside `_rebuild_cholesky`, which is called from `add_ticker` and `remove_ticker`. If a numerical edge case (e.g., all tickers in the same group, near-unit correlation) produces a singular matrix, the exception propagates out of the async `add_ticker` call, crashing that coroutine — the ticker is never added to the simulation, but the cache has no price for it. The simulator continues running but the new ticker silently has no data.

**Fix**: Wrap in a try/except and apply a small regularisation if Cholesky fails:
```python
try:
    self._cholesky = np.linalg.cholesky(corr)
except np.linalg.LinAlgError:
    corr += np.eye(n) * 1e-6  # small regularisation
    self._cholesky = np.linalg.cholesky(corr)
```

---

#### B3 — Version/snapshot race in SSE generator (`stream.py:66-72` + `cache.py:47`)

```python
# In _generate_events:
current_version = price_cache.version  # read 1 (no lock)
if current_version != last_version:
    prices = price_cache.get_all()     # read 2 (separate lock acquisition)
```

Between reading `version` and calling `get_all()`, the background task can write another update, incrementing `_version` again. The SSE event is sent with the price snapshot from read 2 but tagged against the version from read 1. On the next cycle, `current_version` equals the already-captured value, so the client misses the intermediate update. In practice this is cosmetically benign (the next tick catches up), but it means the version-based change detection has a one-tick blind spot under load.

**Fix**: Read version and snapshot atomically by adding a combined method to `PriceCache`:
```python
def get_snapshot(self) -> tuple[int, dict[str, PriceUpdate]]:
    with self._lock:
        return self._version, dict(self._prices)
```

---

#### B4 — `SimulatorDataSource.add_ticker` not normalizing ticker format (`simulator.py:199-205`)

`MassiveDataSource.add_ticker` normalizes to uppercase and strips whitespace; `SimulatorDataSource.add_ticker` does not. A ticker added as `"tcs"` or `"  TCS  "` via the watchlist API would be tracked by the simulator under the wrong key, get no SSE updates, and the API response for `GET /api/watchlist` would show a mismatched symbol.

**Fix**: Add `ticker = ticker.upper().strip()` at the start of `SimulatorDataSource.add_ticker` and `remove_ticker`.

---

### DESIGN — Technical Debt

#### D1 — Module-level `router` mutated inside factory (`stream.py:12-24`)

```python
router = APIRouter(prefix="/api/stream", tags=["streaming"])  # module-level singleton

def create_stream_router(price_cache: PriceCache) -> APIRouter:
    @router.get("/prices")   # mutates the module-level object
    async def stream_prices(...):
        ...
    return router            # returns the same singleton
```

Every call to `create_stream_router()` registers an **additional** route on the same `APIRouter` object. The function is called once in production, but in the test suite each test that creates an app instance calls it again, silently registering duplicate routes. FastAPI silently keeps the first registered handler, so the `price_cache` passed to subsequent calls is ignored. This is currently masked by the lack of stream tests.

**Fix**: Move `router = APIRouter(...)` inside `create_stream_router` so a fresh router is created per call.

---

#### D2 — Per-tick constant recomputation in GBM hot path (`simulator.py:112-115`)

```python
drift = (mu - 0.5 * sigma**2) * self._dt      # constant per ticker — recomputed every tick
diffusion = sigma * math.sqrt(self._dt) * z    # sigma*sqrt(dt) is constant — recomputed every tick
```

`drift` and `sigma * sqrt(dt)` are pure functions of per-ticker constants (`mu`, `sigma`) and the global `dt`. They never change between steps. At 500ms intervals with 10 tickers, these are recomputed 20 times/second for no reason.

**Fix**: Precompute in `_add_ticker_internal`:
```python
params["drift"] = (mu - 0.5 * sigma**2) * self._dt
params["sigma_sqrt_dt"] = sigma * math.sqrt(self._dt)
```
Then in `step()`: `diffusion = params["sigma_sqrt_dt"] * z_correlated[i]`.

---

#### D3 — GBM time step uses US market hours (`seed_prices.py:36`)

```python
TRADING_SECONDS_PER_YEAR = 252 * 6.5 * 3600  # NYSE: 9:30–16:00
```

NSE/BSE trades 6.25 hours/day (9:15–15:30 IST), not 6.5. The error is ~4% and slightly over-states drift and volatility per tick. Minor, but inconsistent with the project's Indian market focus.

**Fix**: `TRADING_SECONDS_PER_YEAR = 252 * 6.25 * 3600`.

---

### TEST GAPS

#### T1 — `stream.py` has zero functional tests

The SSE endpoint (the primary user-facing feature) has 33% coverage and no tests for:
- Response `Content-Type: text/event-stream`
- `retry: 1000\n\n` as the first event
- Correct JSON payload shape per `PriceUpdate.to_dict()`
- Version-based deduplication (no event if cache unchanged)
- Client disconnect cleanup

Use FastAPI's `TestClient` with `httpx` in streaming mode to test the generator without a running server.

---

#### T2 — No test for `timestamp=0.0` in `PriceCache.update`

Bug B1 (`timestamp or time.time()`) is not caught by any test. A specific test for zero-epoch timestamp would have caught it.

---

#### T3 — `uv run pytest` fails; tests only pass via `.venv/bin/pytest`

The `uv run` command uses the globally-installed pytest binary, not the venv's, so `massive` is not found. Add `pytest` and `pytest-asyncio` to `[project.optional-dependencies].dev` **and** add this to `pyproject.toml`:

```toml
[tool.uv.scripts]
test = "pytest tests/"
```

Then `uv run test` works correctly. Alternatively, document `.venv/bin/pytest` explicitly in `backend/README.md`.

---

#### T4 — Deprecated `event_loop_policy` fixture in `tests/conftest.py`

```
PytestDeprecationWarning: Overriding the "event_loop_policy" fixture is deprecated
```

The `event_loop_policy` fixture in `tests/conftest.py` is deprecated in `pytest-asyncio`. Remove it — the default policy is already `asyncio.DefaultEventLoopPolicy()`.

---

## Summary Table

| # | Severity | File | Issue |
|---|---|---|---|
| C1 | Critical | `factory.py:13` | Reads `MASSIVE_API_KEY` instead of `TAPETIDE_API_KEY` |
| C2 | Critical | `massive_client.py` | `MassiveDataSource` must be replaced with `TapetidePoller` |
| C3 | Critical | `seed_prices.py` | US tickers/USD prices; must be replaced with NSE/INR data |
| B1 | Bug | `cache.py:18` | `timestamp or time.time()` overwrites zero timestamps |
| B2 | Bug | `simulator.py:160` | Unhandled `LinAlgError` from Cholesky on singular matrix |
| B3 | Bug | `stream.py:66` | Version/snapshot read is not atomic; one-tick blind spot |
| B4 | Bug | `simulator.py:199` | Ticker not normalised (uppercase/strip) in `SimulatorDataSource` |
| D1 | Design | `stream.py:12` | Module-level router mutated by factory; duplicate routes on re-call |
| D2 | Design | `simulator.py:112` | Drift and sigma constants recomputed every 500ms tick |
| D3 | Design | `seed_prices.py:36` | Trading hours constant uses NYSE hours, not NSE |
| T1 | Test gap | `stream.py` | No functional tests for SSE endpoint (33% coverage) |
| T2 | Test gap | `test_cache.py` | No test for `timestamp=0.0` (would catch B1) |
| T3 | Test gap | `pyproject.toml` | `uv run pytest` fails; requires `.venv/bin/pytest` |
| T4 | Test gap | `tests/conftest.py` | Deprecated `event_loop_policy` fixture generates 73 warnings |

---

## What's Working Well

- **Abstract interface design** is clean and correctly separates concerns. The `MarketDataSource` ABC + `PriceCache` hub pattern will carry forward to `TapetidePoller` unchanged.
- **GBM simulator implementation** is mathematically correct (proper Itô calculus, Cholesky for correlations, random shock events). It's production-quality for a simulated market.
- **`PriceCache` threading** is correctly designed — all mutations are lock-protected, immutable `PriceUpdate` objects prevent stale reads.
- **Error handling in `MassiveDataSource._poll_once`** is defensive and correct: bad snapshots are skipped individually; API failures don't crash the poller.
- **Test coverage** is excellent for an early implementation: 91% overall, 100% on the four core modules.
- **Code style** is consistent and idiomatic Python 3.12. Ruff passes with zero warnings.

---

## Priority Order for Next Agent

1. **Implement `TapetidePoller`** (C2) — the `MarketDataSource` interface and `PriceCache` are ready; just need the new class in `backend/app/market/tapetide_client.py`.
2. **Update `seed_prices.py`** (C3) — replace US data with NSE tickers and INR seed prices.
3. **Update `factory.py`** (C1) — read `TAPETIDE_API_KEY`, instantiate `TapetidePoller`.
4. **Fix `cache.py:18`** (B1) — `timestamp is not None` check.
5. **Fix `stream.py` router** (D1) — move `APIRouter(...)` inside the factory function.
6. **Fix ticker normalization** (B4) — add `upper().strip()` in `SimulatorDataSource`.
7. **Add SSE tests** (T1) — at minimum test response headers and payload shape.
8. **Precompute GBM constants** (D2) — low effort, eliminates unnecessary work in the hot path.
