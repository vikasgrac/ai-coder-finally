# Market Data Backend — Code Review

**Reviewer**: Claude Code (claude-sonnet-4-6)  
**Date**: 2026-06-07  
**Branch reviewed**: `claude/issue-3-20260607-0158` (commit `c6e81fa` — "feat: implement market data backend (interface, simulator, Tapetide)")  
**Scope**: `backend/app/market_data/` (4 modules, ~250 SLOC) + `backend/tests/` (84 tests across 3 files)

> **Note**: An earlier review was written against the old `6a2b36e` commit (the previous Massive/Polygon.io implementation). This document supersedes that — it reviews the correct, current implementation.

---

## Test Run Results

**84 tests collected** (not 97).

| Run | Passed | Failed |
|-----|--------|--------|
| 1 | 83 | 1 |
| 2 | 83 | 1 |
| 3 | 82 | 2 |
| 4 | 83 | 1 |
| 5 | 83 | 1 |

- **1 deterministic failure**: `test_interface.py::TestMarketDataInterfaceMethods::test_start_with_multiple_tickers` — fails every run.
- **1 flaky failure**: `test_simulator.py::TestSectorCorrelation::test_it_stocks_move_together` — fails ~20% of runs (probabilistic test with insufficient samples).

### Coverage Summary

| Module | Coverage | Uncovered lines |
|---|---|---|
| `interface.py` | **100%** | — |
| `simulator.py` | **97%** | 132 (event log), 178 (edge guard) |
| `tapetide.py` | **88%** | 29 (import branch), 109-112 (poll loop body), 116-117 (micro loop body), 125 (fastmcp call), 130-141 (response parsing branches), 243 (zero-price guard) |
| `__init__.py` | **60%** | 25-28 (factory branches — no test exercises the factory) |
| **Total** | **91%** | |

---

## Failing Tests

### F1 — `test_start_with_multiple_tickers` (always fails)

**Root cause**: `_Minimal.start()` in `test_interface.py` only sets `self._running = True` — it does not call `add_ticker()` for each ticker. The test then asserts those tickers appear in the price cache, which they don't.

```python
# _Minimal.start() — incomplete:
async def start(self, tickers):
    self._running = True          # ← doesn't add tickers to the cache

# Test assertion fails:
assert set(all_prices.keys()) == {"RELIANCE", "TCS", "INFY"}
# actual: set()
```

**Fix** — update `_Minimal.start()` to loop through tickers:
```python
async def start(self, tickers):
    self._running = True
    for ticker in tickers:
        await self.add_ticker(ticker)
```

---

### F2 — `test_it_stocks_move_together` (flaky, ~20% failure rate)

**Root cause**: The test measures correlation over only 200 price steps and asserts that TCS/INFY correlation exceeds TCS/SBIN correlation. With 50% idiosyncratic noise per step, 200 samples are insufficient — sample correlation can easily fall below the cross-sector value by chance. This is a statistical power issue.

```python
for _ in range(200):    # ← too few samples for reliable correlation estimate
    s._step()
```

**Fix**: Increase to 1000+ steps, or use `pytest.mark.flaky` with a retry budget, or restructure as a deterministic test using a fixed random seed:
```python
import numpy as np
np.random.seed(42)
random.seed(42)
for _ in range(1000):
    s._step()
```

---

## Correctness Bugs

### B1 — Falsy-zero price silently ignored in `_update_from_quote` (`tapetide.py:~170`)

```python
price = (
    quote.get("price")
    or quote.get("last_price")
    or quote.get("ltp")
)
```

A legitimate price of `0.0` is falsy and causes the expression to fall through to `None`. The same pattern appears in `_update_from_quote_dict`. For Indian stocks this is cosmetically benign (no NSE stock trades at ₹0), but it's a semantic bug that silently drops updates on circuit-breaker halts or malformed data.

**Fix**: `price = quote.get("price") if "price" in quote else quote.get("last_price") if "last_price" in quote else quote.get("ltp")`

Or more clearly:
```python
for key in ("price", "last_price", "ltp"):
    price = quote.get(key)
    if price is not None:
        break
```

---

### B2 — Ticker stuck at ₹0 if initial Tapetide poll fails (`tapetide.py:add_ticker`, `_apply_micro_moves`)

`add_ticker()` seeds the cache with `price=0.0`. `_apply_micro_moves()` skips tickers with `price <= 0`:

```python
if current.price <= 0:
    continue  # not yet seeded from a real poll
```

If `_poll_tapetide()` fails at startup (network error, bad API key, `fastmcp` bug), the ticker stays at ₹0.0 permanently. Micro-moves keep skipping it. The SSE stream broadcasts `price=0` to the frontend indefinitely — no recovery until the next successful poll.

**Fix**: Seed with the simulator's `SEED_PRICES` as a fallback, or use `DEFAULT_SEED_PRICE` as the initial price instead of `0.0`:
```python
from app.market_data.simulator import SEED_PRICES, DEFAULT_SEED_PRICE
seed = SEED_PRICES.get(ticker, DEFAULT_SEED_PRICE)
self._price_cache[ticker] = PriceData(ticker=ticker, price=seed, ...)
```

---

### B3 — `_process_quotes` falls through to wrong branch when all TextContent items have unparseable JSON (`tapetide.py:~196`)

```python
if isinstance(result, list):
    for item in result:
        text = getattr(item, "text", None)
        if text:
            try:
                raw = json.loads(text)
                break
            except (json.JSONDecodeError, TypeError):
                continue
    else:
        # result was a plain Python list (e.g. from tests)
        if result and not hasattr(result[0], "text"):
            raw = result
```

If every item in `result` has a `.text` attribute but each fails `json.loads` (e.g., all malformed), the `for/else` branch runs. But `result[0]` does have `.text` (it's a FastMCP `TextContent` object), so `not hasattr(result[0], "text")` is `False`, and `raw` remains the original `result` (a list of `TextContent` objects). The code then tries `for item in raw: self._update_from_quote(item, now)` — but each `item` is a `TextContent` object, not a dict, so every `.get()` call fails silently (returns `None`). No prices are updated, no exception is raised, the failure is completely silent.

**Fix**: Set `raw = []` as the fallback when no valid JSON is found, so the subsequent loop does nothing and the failure is explicit (via the existing `logger.error` in `_poll_tapetide`'s except clause).

---

### B4 — `PriceData` is mutable; cache can be corrupted by callers (`interface.py:12`)

```python
@dataclass
class PriceData:
    ticker: str
    price: float
    ...
```

`get_all_prices()` returns a copy of the outer dict, but the `PriceData` values are the same objects. Any caller can do:
```python
data = provider.get_all_prices()
data["RELIANCE"].price = 0.0  # corrupts the live cache
```

**Fix**: Add `frozen=True`:
```python
@dataclass(frozen=True)
class PriceData:
```

---

## Design Issues

### D1 — Factory function (`__init__.py`) has 0% test coverage

`create_market_data_provider()` is the primary entry point but neither path (simulator nor TapetidePoller) is exercised by any test. The factory function also has no test for the whitespace-only API key case.

**Fix**: Add a `TestFactory` class:
```python
def test_no_key_returns_simulator(monkeypatch):
    monkeypatch.delenv("TAPETIDE_API_KEY", raising=False)
    assert isinstance(create_market_data_provider(), MarketSimulator)

def test_key_returns_tapetide(monkeypatch):
    monkeypatch.setenv("TAPETIDE_API_KEY", "test-key")
    assert isinstance(create_market_data_provider(), TapetidePoller)

def test_whitespace_key_returns_simulator(monkeypatch):
    monkeypatch.setenv("TAPETIDE_API_KEY", "   ")
    assert isinstance(create_market_data_provider(), MarketSimulator)
```

---

### D2 — Subclasses must directly mutate `_price_cache`; no thread-safety (`interface.py`)

The base class exposes `self._price_cache` as a plain `dict` that subclasses write to directly. There is no lock. In the TapetidePoller, `_poll_task` (running `_poll_tapetide`) and `_micro_task` (running `_apply_micro_moves`) both write to `_price_cache` concurrently as asyncio tasks. Because asyncio is single-threaded and neither write contains an `await`, individual dict assignments are safe — but it's a fragile design that will break if any future writer uses threads (`asyncio.to_thread`, `ThreadPoolExecutor`).

The old implementation's dedicated `PriceCache` with an explicit `threading.Lock` was safer. Consider adding a comment to `interface.py` documenting the concurrency contract.

---

### D3 — `MarketSimulator._step` uses a shared `group_shocks` dict but tickers iterate over `self._tickers` which could change (`simulator.py:114`)

```python
def _step(self) -> None:
    group_shocks = {i: random.gauss(0, 1) for i in range(len(CORRELATION_GROUPS))}
    for ticker in list(self._tickers):  # list() snapshots tickers
```

The `list(self._tickers)` defensively snapshots the set, which is correct. The `group_shocks` dict is pre-computed once per step — also correct. No issue here, just noting the correct defensive pattern.

---

### D4 — `test_gbm_log_returns_are_normal` in `test_simulator.py` is slow (generates 10,000 steps)

The test runs 10,000 `_step()` calls inline. Each step iterates over 5 tickers, computing log returns. It takes ~2s per run. This isn't a bug, but it slows down the test suite for other developers. Consider reducing to 2,000 steps (still enough for a Shapiro-Wilk test) or marking it `@pytest.mark.slow`.

---

## What's Working Well

The new implementation is a major improvement over the old one on every dimension that matters:

- **Correct environment variable** — `TAPETIDE_API_KEY`, not `MASSIVE_API_KEY`.
- **`TapetidePoller` implemented** — FastMCP client with lazy `fastmcp` import for graceful degradation; the `try/except ImportError` pattern means tests run without installing fastmcp.
- **NSE tickers and INR seed prices** — RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK, HINDUNILVR, SBIN, WIPRO, BAJFINANCE, TATAMOTORS at correct INR values.
- **Hybrid polling model** — real Tapetide poll every 10s + low-volatility GBM micro-moves every 500ms. Exactly matches the spec.
- **Indian sector correlation groups** — IT (TCS, INFY, WIPRO), Banking (HDFCBANK, ICICIBANK, SBIN, BAJFINANCE), vs the old US tech/finance groups.
- **Simpler architecture** — `_price_cache` dict on the base class, no separate `PriceCache` wrapper. Cleaner for a single-writer model.
- **Excellent `_process_quotes` flexibility** — handles list-of-dicts, dict-of-dicts, flat price values, and FastMCP TextContent items. Well-tested with dedicated test class.
- **`PriceData` is a dataclass** — clean, equality-supporting, sensible field names.
- **`fastmcp` is optional at import time** — `TapetidePoller` can be imported and tested without `fastmcp` installed.

---

## Summary Table

| # | Severity | Location | Issue |
|---|---|---|---|
| F1 | **Test failure** | `test_interface.py:160` | `_Minimal.start()` doesn't call `add_ticker()`, so `test_start_with_multiple_tickers` always fails |
| F2 | **Flaky test** | `test_simulator.py:213` | Correlation test uses 200 samples — insufficient statistical power (~20% false failure rate) |
| B1 | Bug | `tapetide.py:~170` | `quote.get("price") or ...` treats `0.0` as falsy, silently drops zero-price updates |
| B2 | Bug | `tapetide.py:add_ticker` | Seeds price at `0.0`; micro-moves skip forever if initial Tapetide poll fails |
| B3 | Bug | `tapetide.py:_process_quotes` | When all TextContent items have invalid JSON, falls through to iterate TextContent objects as dicts — silent no-op |
| B4 | Bug | `interface.py:12` | `PriceData` is mutable; callers can corrupt the live cache via `get_all_prices()` |
| D1 | Design/test gap | `__init__.py:create_market_data_provider` | Factory function completely untested (60% coverage) |
| D2 | Design | `interface.py` | `_price_cache` is an unguarded mutable dict; no concurrency contract documented |

---

## Priority Fix Order

1. **Fix F1** (2 lines): add the ticker loop inside `_Minimal.start()` — unblocks CI.
2. **Fix B4** (1 character): `@dataclass(frozen=True)` — prevents cache corruption.
3. **Fix B1** (5 lines): replace `or`-chain with `next((v for k, v in ... if v is not None), None)` pattern.
4. **Fix B2** (3 lines): seed `TapetidePoller.add_ticker` with `SEED_PRICES.get(ticker, DEFAULT_SEED_PRICE)` instead of `0.0`.
5. **Fix F2** (1 number): increase step count from 200 → 1000, or add `random.seed(42)`.
6. **Add factory tests** (D1): 3 tests, ~20 lines.
7. **Fix B3** (2 lines): `raw = []` as fallback in the `for/else` branch.
