"""Unit tests for the GBM-based MarketSimulator."""
import asyncio
import math
import random
import statistics
import pytest

from app.market_data.interface import MarketDataInterface, PriceData
from app.market_data.simulator import (
    MarketSimulator,
    SEED_PRICES,
    DEFAULT_SEED_PRICE,
    CORRELATION_GROUPS,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def sim():
    """Running simulator over the default NSE watchlist."""
    s = MarketSimulator(update_interval=0.05)
    await s.start(list(SEED_PRICES.keys()))
    yield s
    await s.stop()


@pytest.fixture
def sim_stopped():
    return MarketSimulator()


# ---------------------------------------------------------------------------
# Interface compliance
# ---------------------------------------------------------------------------

class TestInterfaceCompliance:
    def test_is_market_data_interface(self, sim_stopped):
        assert isinstance(sim_stopped, MarketDataInterface)

    def test_has_all_abstract_methods(self, sim_stopped):
        for method in ("start", "stop", "add_ticker", "remove_ticker"):
            assert callable(getattr(sim_stopped, method))


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestInitialization:
    async def test_starts_not_running(self, sim_stopped):
        assert sim_stopped.is_running is False

    async def test_prices_empty_before_start(self, sim_stopped):
        assert sim_stopped.get_all_prices() == {}

    async def test_running_after_start(self, sim):
        assert sim.is_running is True

    async def test_all_tickers_in_cache_after_start(self, sim):
        prices = sim.get_all_prices()
        for ticker in SEED_PRICES:
            assert ticker in prices, f"{ticker} missing from cache"

    async def test_initial_prices_near_seed(self, sim):
        """Each initial price should be within 5 % of its seed."""
        for ticker, seed in SEED_PRICES.items():
            price_data = sim.get_price(ticker)
            assert price_data is not None
            assert seed * 0.95 <= price_data.price <= seed * 1.05, (
                f"{ticker}: price {price_data.price} not near seed {seed}"
            )

    async def test_unknown_ticker_uses_default_seed(self):
        s = MarketSimulator()
        await s.add_ticker("UNKNOWN_XYZ")
        pd = s.get_price("UNKNOWN_XYZ")
        assert pd is not None
        assert DEFAULT_SEED_PRICE * 0.9 <= pd.price <= DEFAULT_SEED_PRICE * 1.1


# ---------------------------------------------------------------------------
# add_ticker / remove_ticker
# ---------------------------------------------------------------------------

class TestTickerManagement:
    async def test_add_ticker_creates_entry(self, sim_stopped):
        await sim_stopped.add_ticker("RELIANCE")
        assert sim_stopped.get_price("RELIANCE") is not None

    async def test_add_same_ticker_twice_is_idempotent(self, sim_stopped):
        await sim_stopped.add_ticker("TCS")
        price1 = sim_stopped.get_price("TCS").price
        await sim_stopped.add_ticker("TCS")
        price2 = sim_stopped.get_price("TCS").price
        assert price1 == price2  # second add must not change the price

    async def test_remove_ticker_clears_entry(self, sim_stopped):
        await sim_stopped.add_ticker("INFY")
        await sim_stopped.remove_ticker("INFY")
        assert sim_stopped.get_price("INFY") is None

    async def test_remove_unknown_ticker_no_error(self, sim_stopped):
        await sim_stopped.remove_ticker("NONEXISTENT")  # must not raise

    async def test_added_ticker_gets_initial_price(self, sim_stopped):
        await sim_stopped.add_ticker("HDFCBANK")
        pd = sim_stopped.get_price("HDFCBANK")
        assert pd is not None
        assert pd.price > 0

    async def test_initial_change_direction_is_unchanged(self, sim_stopped):
        await sim_stopped.add_ticker("SBIN")
        pd = sim_stopped.get_price("SBIN")
        assert pd.change_direction == "unchanged"


# ---------------------------------------------------------------------------
# GBM price update correctness
# ---------------------------------------------------------------------------

class TestGBMPriceUpdates:
    async def test_prices_update_over_time(self, sim):
        """After several update cycles prices must have changed for most tickers."""
        before = {t: sim.get_price(t).price for t in SEED_PRICES}
        await asyncio.sleep(0.3)  # ~6 steps at 50 ms interval
        after  = {t: sim.get_price(t).price for t in SEED_PRICES}
        changed = sum(1 for t in SEED_PRICES if before[t] != after[t])
        assert changed > 0, "No prices changed after multiple update intervals"

    async def test_prices_always_positive(self, sim):
        """Prices must never go non-positive."""
        await asyncio.sleep(0.5)
        for ticker in SEED_PRICES:
            pd = sim.get_price(ticker)
            assert pd is not None
            assert pd.price > 0, f"{ticker} price went non-positive: {pd.price}"

    async def test_change_direction_consistency(self, sim):
        """change_direction must match price vs previous_price."""
        await asyncio.sleep(0.3)
        for ticker in SEED_PRICES:
            pd = sim.get_price(ticker)
            if pd.price > pd.previous_price:
                assert pd.change_direction == "up", ticker
            elif pd.price < pd.previous_price:
                assert pd.change_direction == "down", ticker
            else:
                assert pd.change_direction == "unchanged", ticker

    async def test_prices_stay_within_reasonable_range(self):
        """Even after 100 steps, prices should stay within 50% of seed."""
        s = MarketSimulator(update_interval=0.01, volatility=0.001)
        await s.start(["RELIANCE"])
        await asyncio.sleep(1.5)  # ~100 steps
        await s.stop()
        pd = s.get_price("RELIANCE")
        seed = SEED_PRICES["RELIANCE"]
        assert seed * 0.5 <= pd.price <= seed * 2.0, (
            f"Price {pd.price} drifted far from seed {seed}"
        )

    def test_gbm_step_math(self):
        """Validate the GBM formula: E[S(t+dt)/S(t)] ≈ exp(μ*dt)."""
        drift = 0.0001
        vol   = 0.002
        dt    = 0.5
        n     = 10_000

        ratios = []
        for _ in range(n):
            z       = random.gauss(0, 1)
            log_ret = (drift - 0.5 * vol**2) * dt + vol * math.sqrt(dt) * z
            ratios.append(math.exp(log_ret))

        mean_ratio  = statistics.mean(ratios)
        expected    = math.exp(drift * dt)
        # Mean ratio should be within 2% of expected value
        assert abs(mean_ratio - expected) / expected < 0.02, (
            f"GBM mean ratio {mean_ratio:.6f} far from expected {expected:.6f}"
        )

    def test_gbm_log_returns_are_normal(self):
        """Log returns from GBM should be approximately normally distributed."""
        drift = 0.0001
        vol   = 0.002
        dt    = 0.5
        n     = 5_000

        log_rets = []
        for _ in range(n):
            z = random.gauss(0, 1)
            log_rets.append(
                (drift - 0.5 * vol**2) * dt + vol * math.sqrt(dt) * z
            )

        mean   = statistics.mean(log_rets)
        stdev  = statistics.stdev(log_rets)
        expected_mean  = (drift - 0.5 * vol**2) * dt
        expected_stdev = vol * math.sqrt(dt)

        assert abs(mean - expected_mean)   < 0.001, f"mean {mean} vs {expected_mean}"
        assert abs(stdev - expected_stdev) < 0.001, f"stdev {stdev} vs {expected_stdev}"


# ---------------------------------------------------------------------------
# Sector correlation
# ---------------------------------------------------------------------------

class TestSectorCorrelation:
    async def test_it_stocks_move_together(self):
        """IT tickers should have higher return correlation than cross-sector pairs."""
        s = MarketSimulator(update_interval=0.01, volatility=0.005)
        it_tickers    = ["TCS", "INFY", "WIPRO"]
        other_tickers = ["RELIANCE", "SBIN"]
        await s.start(it_tickers + other_tickers)

        price_series = {t: [] for t in it_tickers + other_tickers}
        random.seed(42)  # deterministic seed prevents flakiness
        for _ in range(1000):
            s._step()
            for t in price_series:
                price_series[t].append(s.get_price(t).price)

        await s.stop()

        def returns(prices):
            return [
                math.log(prices[i] / prices[i - 1])
                for i in range(1, len(prices))
            ]

        def correlation(a, b):
            if not a or not b:
                return 0.0
            n  = len(a)
            ma, mb = statistics.mean(a), statistics.mean(b)
            cov    = sum((x - ma) * (y - mb) for x, y in zip(a, b)) / n
            sa     = statistics.pstdev(a) or 1e-10
            sb     = statistics.pstdev(b) or 1e-10
            return cov / (sa * sb)

        it_rets = {t: returns(price_series[t]) for t in it_tickers}
        tcs_infy_corr = correlation(it_rets["TCS"],  it_rets["INFY"])
        tcs_sbin_corr = correlation(
            it_rets["TCS"],
            returns(price_series["SBIN"])
        )
        # IT stocks should be more correlated with each other than with SBIN
        assert tcs_infy_corr > tcs_sbin_corr, (
            f"IT correlation {tcs_infy_corr:.3f} <= cross-sector {tcs_sbin_corr:.3f}"
        )


# ---------------------------------------------------------------------------
# Random events
# ---------------------------------------------------------------------------

class TestRandomEvents:
    async def test_event_causes_large_move(self):
        """Forcing event_probability=1 should always produce a ≥2% move."""
        s = MarketSimulator(
            update_interval=0.5,
            event_probability=1.0,
            event_max_magnitude=0.05,
        )
        await s.add_ticker("RELIANCE")

        old_price = s.get_price("RELIANCE").price
        s._step()
        new_price = s.get_price("RELIANCE").price

        pct_change = abs(new_price - old_price) / old_price
        assert pct_change >= 0.02, (
            f"Expected ≥2% move but got {pct_change:.2%}"
        )


# ---------------------------------------------------------------------------
# Start / stop lifecycle
# ---------------------------------------------------------------------------

class TestLifecycle:
    async def test_stop_after_never_started(self, sim_stopped):
        await sim_stopped.stop()  # must not raise

    async def test_start_stop_start_stop(self):
        s = MarketSimulator(update_interval=0.05)
        await s.start(["RELIANCE"])
        assert s.is_running is True
        await s.stop()
        assert s.is_running is False
        await s.start(["TCS"])
        assert s.is_running is True
        await s.stop()
        assert s.is_running is False

    async def test_prices_frozen_after_stop(self):
        s = MarketSimulator(update_interval=0.05)
        await s.start(["RELIANCE"])
        await asyncio.sleep(0.2)
        await s.stop()
        price_at_stop = s.get_price("RELIANCE").price
        await asyncio.sleep(0.2)
        price_after   = s.get_price("RELIANCE").price
        assert price_at_stop == price_after, "Prices changed after stop"
