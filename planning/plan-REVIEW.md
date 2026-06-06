# PLAN.md Review

## Internal Consistency Issues

**[HIGH] Stale "Massive API" reference in Section 3.**
Architecture Overview still says "real data via Massive API if key provided" — contradicts the resolved Section 13 item. Should say Tapetide.

**[HIGH] Structured output schema uses US tickers as examples.**
Section 9 shows `"ticker": "AAPL"` / `"PYPL"`. Should use NSE examples (RELIANCE, TCS) to avoid agents generating wrong formats.

**[MEDIUM] E2E test scenario refers to "$10k balance".**
Section 12 says "default watchlist appears, $10k balance shown" — should be ₹1,00,000.

**[MEDIUM] `users_profile` schema column default contradicts seed data.**
Column default is `10000.0` but seed data block says `100000.0 (₹1,00,000)`. Leftover from the US-dollar era.

**[LOW] Section 6 "Shared Price Cache" still mentions "Massive poller".**
Should say TapetidePoller.

---

## Completeness Gaps

**[HIGH] No SSE event schema defined.**
Section 6 lists the fields verbally but gives no JSON field names or types. Frontend and backend agents will invent incompatible names (`prev_price` vs `previousPrice`).

**[HIGH] API response shapes are not defined.**
Section 8 describes endpoints but gives no example JSON for `/api/portfolio`, `/api/watchlist` (GET), or `/api/portfolio/history`.

**[HIGH] LLM mock response content is unspecified.**
Section 9 says `LLM_MOCK=true` returns deterministic responses but never defines their content. E2E tests asserting "trade execution appears inline" will be unverifiable.

**[MEDIUM] No ticker validation or normalisation rules.**
NSE tickers can include special characters (`M&M`), casing variations, or `.NS` suffixes. Spec is silent on normalisation or rejection logic.

**[MEDIUM] `watchlist_changes` valid action values not enumerated.**
Only `"add"` is shown — presumably `"remove"` also exists, but the spec never lists all valid values.

**[MEDIUM] Behaviour on full position sell is unspecified.**
Does the `positions` row get deleted or set to `quantity=0`? Heatmap rendering depends on this.

**[MEDIUM] `total_value` definition in `portfolio_snapshots` is unspecified.**
Cash + market value, or market value only? Must be consistent between snapshot task and `/api/portfolio`.

**[LOW] Chat history window size is unspecified.**
"Loads recent conversation history" with no message count bound → unbounded cost and latency growth.

---

## Technical Correctness Issues

**[HIGH] Static Next.js export breaks with dynamic routes.**
`output: 'export'` requires `generateStaticParams` for any dynamic route. Spec should state no dynamic Next.js routes are to be used.

**[MEDIUM] SQLite WAL mode is not mentioned.**
Without `PRAGMA journal_mode=WAL` at init, concurrent async writes from the snapshot task and trade endpoint will produce "database is locked" errors.

**[MEDIUM] `uv.lock` is deleted in current git state.**
`git status` shows `D backend/uv.lock`. The Dockerfile runs `uv sync`, which requires the lockfile — Docker build will fail.

**[MEDIUM] Native `EventSource` cannot send custom headers.**
No issue now (no auth), but the noted future multi-user path would require replacing it with a `fetch`-based SSE client.

**[LOW] GBM random events use an unseeded RNG.**
Non-deterministic across restarts; can cause E2E test flakes if any assertion touches price ranges.

---

## Clarity / Ambiguity Issues

**[MEDIUM] "Daily change %" has no defined data source.**
SSE only carries current price and previous tick. No concept of trading day open/close in the simulator. Should either remove this column or define the computation (e.g., % change since first price received since page load).

**[MEDIUM] Main chart data source is undefined.**
No `/api/prices/history/{ticker}` endpoint exists. Spec should clarify whether the chart is built from SSE data accumulated since page load.

**[MEDIUM] "Lazy init on startup (or first request)" is ambiguous.**
If deferred to first request, `/api/health` may return 200 before the DB is ready. Spec should commit to startup initialization.

**[LOW] Collapsible chat panel default state is unspecified.**
No stated default (open vs. collapsed) will lead to inconsistent layout decisions.

---

## Risk Areas

**[HIGH] No rate limiting on `/api/chat`.**
Each call triggers a paid LLM call. A retry loop or bug could generate unexpected charges. A simple per-minute cap should be specified.

**[HIGH] LLM auto-executes trades with no size bounds.**
Financial constraints are validated, but not nonsensical quantities (`quantity: 999999`). A per-trade max quantity and a max trades-per-response bound should be added.

**[MEDIUM] In-memory price cache is lost on container restart.**
Prices reset to seed values until next Tapetide poll. Acceptable for a demo but should be explicitly stated so agents don't try to persist it.

**[MEDIUM] `M&M` and similar NSE tickers will break `DELETE /api/watchlist/{ticker}`.**
Ampersands in path parameters must be URL-encoded by the frontend and decoded by the backend — the spec should state this requirement.

**[LOW] SQLite file path in the container is not anchored.**
If the backend resolves `db/finally.db` as a relative path, it breaks depending on uvicorn's working directory. A `DB_PATH` env var or `__file__`-relative anchor should be specified.

---

## Simplification Opportunities

- UUID primary keys on `watchlist` and `positions` add overhead; `(user_id, ticker)` composite PKs would suffice since those are the actual lookup keys.
- The 30-second snapshot background task could be merged into the market-data loop (every N ticks) rather than running as a separate timer.
- `chat_messages.actions` is denormalised data that could drift from the authoritative `trades` and `watchlist` tables; it could be removed entirely since Section 13 already documents it as UI-display-only.

---

## Priority Summary

Most urgent before implementation begins:
1. Define the SSE event JSON schema (field names and types)
2. Define API response shapes for `/api/portfolio`, `/api/watchlist`, `/api/portfolio/history`
3. Fix the stale "Massive API" reference in Section 3
4. Pin the LLM mock fixture content for E2E tests
5. Add a rate-limit policy for `/api/chat`
