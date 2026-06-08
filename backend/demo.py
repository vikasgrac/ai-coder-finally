"""
FinAlly Market Data Demo
Showcases MarketSimulator (GBM) and optionally TapetidePoller (live NSE data).
Run: uv run python demo.py [--live]
"""
import asyncio
import os
import sys
import time
from datetime import datetime

# ── ANSI helpers ─────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
RED    = "\033[31m"
YELLOW = "\033[33m"
CYAN   = "\033[36m"
WHITE  = "\033[37m"
CLEAR  = "\033[2J\033[H"   # clear screen + move cursor to top


def colored(text: str, code: str) -> str:
    return f"{code}{text}{RESET}"


# ── Layout constants ──────────────────────────────────────────────────────────

TICKERS = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "HINDUNILVR", "SBIN", "WIPRO", "BAJFINANCE", "TATAMOTORS",
]

COL_TICKER = 12
COL_PRICE  = 10
COL_PREV   = 10
COL_CHANGE = 9
COL_DIR    = 8


def header() -> str:
    line = (
        f"{'TICKER':<{COL_TICKER}}"
        f"{'PRICE':>{COL_PRICE}}"
        f"{'PREV':>{COL_PREV}}"
        f"{'CHANGE%':>{COL_CHANGE}}"
        f"{'DIR':>{COL_DIR}}"
    )
    sep = "─" * len(line)
    return colored(line, BOLD + CYAN) + "\n" + colored(sep, DIM)


def price_row(pd) -> str:
    change_pct = (pd.price - pd.previous_price) / pd.previous_price * 100
    color = GREEN if pd.change_direction == "up" else RED if pd.change_direction == "down" else WHITE
    arrow = "▲" if pd.change_direction == "up" else "▼" if pd.change_direction == "down" else "─"

    ticker_str = f"{pd.ticker:<{COL_TICKER}}"
    price_str  = f"₹{pd.price:>8.2f}"
    prev_str   = f"₹{pd.previous_price:>8.2f}"
    chg_str    = f"{change_pct:>+7.3f}%"
    dir_str    = f"{arrow:>{COL_DIR}}"

    row = ticker_str + price_str + prev_str + chg_str + dir_str
    return colored(row, color)


def missing_row(ticker: str) -> str:
    return colored(f"{ticker:<{COL_TICKER}}{'--':>{COL_PRICE}}{'--':>{COL_PREV}}{'--':>{COL_CHANGE}}{'?':>{COL_DIR}}", DIM)


def render(provider, mode: str, tick: int, start: float, extra: str = "") -> None:
    prices = provider.get_all_prices()
    elapsed = time.time() - start
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

    lines = [
        CLEAR,
        colored("  FinAlly — Market Data Demo", BOLD + YELLOW),
        colored(f"  Mode: {mode}  |  Tick: {tick}  |  Elapsed: {elapsed:.1f}s  |  {ts}", DIM),
        "",
        "  " + header(),
    ]

    for ticker in TICKERS:
        pd = prices.get(ticker)
        row = price_row(pd) if pd else missing_row(ticker)
        lines.append("  " + row)

    if extra:
        lines.append("")
        lines.append(colored("  " + extra, YELLOW))

    lines.append("")
    lines.append(colored("  Press Ctrl+C to stop", DIM))
    print("\n".join(lines), end="", flush=True)


# ── Simulator demo ────────────────────────────────────────────────────────────

async def run_simulator_demo(duration: float = 20.0) -> None:
    from app.market_data.simulator import MarketSimulator

    sim = MarketSimulator(update_interval=0.5)
    await sim.start(TICKERS)
    start = time.time()
    tick = 0

    try:
        while time.time() - start < duration:
            tick += 1
            remaining = duration - (time.time() - start)

            extra = ""
            if tick == 15:
                await sim.add_ticker("NESTLEIND")
                extra = "★ Added NESTLEIND to watchlist"
            elif tick == 25:
                await sim.remove_ticker("NESTLEIND")
                extra = "✕ Removed NESTLEIND from watchlist"
            elif remaining <= 3:
                extra = f"Wrapping up in {remaining:.0f}s…"

            render(sim, "GBM Simulator (no network)", tick, start, extra)
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        await sim.stop()


# ── TapetidePoller demo ───────────────────────────────────────────────────────

async def run_tapetide_demo(api_key: str, duration: float = 40.0) -> None:
    from app.market_data.tapetide import TapetidePoller

    poller = TapetidePoller(api_key=api_key)
    await poller.start(TICKERS)
    start = time.time()
    tick = 0

    try:
        while time.time() - start < duration:
            tick += 1
            elapsed = time.time() - start
            next_poll = TapetidePoller.POLL_INTERVAL - (elapsed % TapetidePoller.POLL_INTERVAL)
            extra = f"Next Tapetide poll in {next_poll:.1f}s  (micro-moves every 0.5s)"
            render(poller, "TapetidePoller  (live NSE data)", tick, start, extra)
            await asyncio.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        await poller.stop()


# ── Entry point ───────────────────────────────────────────────────────────────

async def main() -> None:
    live = "--live" in sys.argv

    api_key = os.getenv("TAPETIDE_API_KEY", "").strip()
    if live and not api_key:
        print("TAPETIDE_API_KEY not set — falling back to simulator")
        live = False

    if live:
        print(colored("\n  Starting TapetidePoller (live NSE data)…", CYAN), flush=True)
        await asyncio.sleep(0.5)
        await run_tapetide_demo(api_key)
    else:
        print(colored("\n  Starting GBM simulator…", CYAN), flush=True)
        await asyncio.sleep(0.5)
        await run_simulator_demo()

    # After simulator, offer live if key is present
    if not live and api_key:
        print(colored("\n\n  TAPETIDE_API_KEY detected — switching to live NSE data…", YELLOW), flush=True)
        await asyncio.sleep(1.5)
        await run_tapetide_demo(api_key)


if __name__ == "__main__":
    # Load .env from project root (one level up from backend/)
    try:
        from dotenv import load_dotenv
        load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))
    except ImportError:
        pass

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n  Demo stopped.\n")
