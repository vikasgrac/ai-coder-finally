"""Unit tests for MarketDataInterface and PriceData."""
import pytest
from dataclasses import fields

from app.market_data.interface import MarketDataInterface, PriceData


# ---------------------------------------------------------------------------
# PriceData tests
# ---------------------------------------------------------------------------

class TestPriceData:
    def test_is_dataclass(self):
        pd = PriceData(
            ticker="RELIANCE",
            price=1300.0,
            previous_price=1290.0,
            timestamp="2026-01-01T00:00:00+00:00",
            change_direction="up",
        )
        assert pd.ticker == "RELIANCE"
        assert pd.price == 1300.0
        assert pd.previous_price == 1290.0
        assert pd.change_direction == "up"

    def test_field_names(self):
        field_names = {f.name for f in fields(PriceData)}
        assert field_names == {
            "ticker", "price", "previous_price", "timestamp", "change_direction"
        }

    def test_equality(self):
        pd1 = PriceData("TCS", 2200.0, 2190.0, "2026-01-01T00:00:00Z", "up")
        pd2 = PriceData("TCS", 2200.0, 2190.0, "2026-01-01T00:00:00Z", "up")
        assert pd1 == pd2

    def test_inequality(self):
        pd1 = PriceData("TCS", 2200.0, 2190.0, "2026-01-01T00:00:00Z", "up")
        pd2 = PriceData("TCS", 2201.0, 2190.0, "2026-01-01T00:00:00Z", "up")
        assert pd1 != pd2

    def test_change_directions(self):
        for direction in ("up", "down", "unchanged"):
            pd = PriceData("X", 100.0, 100.0, "2026-01-01T00:00:00Z", direction)
            assert pd.change_direction == direction


# ---------------------------------------------------------------------------
# MarketDataInterface abstract class tests
# ---------------------------------------------------------------------------

class TestMarketDataInterfaceAbstract:
    def test_cannot_instantiate_abstract(self):
        with pytest.raises(TypeError):
            MarketDataInterface()  # type: ignore[abstract]

    def test_concrete_must_implement_start(self):
        class Incomplete(MarketDataInterface):
            async def stop(self): pass
            async def add_ticker(self, t): pass
            async def remove_ticker(self, t): pass

        with pytest.raises(TypeError):
            Incomplete()

    def test_concrete_must_implement_stop(self):
        class Incomplete(MarketDataInterface):
            async def start(self, t): pass
            async def add_ticker(self, t): pass
            async def remove_ticker(self, t): pass

        with pytest.raises(TypeError):
            Incomplete()

    def test_concrete_must_implement_add_ticker(self):
        class Incomplete(MarketDataInterface):
            async def start(self, t): pass
            async def stop(self): pass
            async def remove_ticker(self, t): pass

        with pytest.raises(TypeError):
            Incomplete()

    def test_concrete_must_implement_remove_ticker(self):
        class Incomplete(MarketDataInterface):
            async def start(self, t): pass
            async def stop(self): pass
            async def add_ticker(self, t): pass

        with pytest.raises(TypeError):
            Incomplete()


# ---------------------------------------------------------------------------
# MarketDataInterface shared methods via a minimal concrete implementation
# ---------------------------------------------------------------------------

class _Minimal(MarketDataInterface):
    async def start(self, tickers):
        self._running = True

    async def stop(self):
        self._running = False

    async def add_ticker(self, ticker):
        from datetime import datetime, timezone
        self._price_cache[ticker] = PriceData(
            ticker=ticker,
            price=100.0,
            previous_price=100.0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            change_direction="unchanged",
        )

    async def remove_ticker(self, ticker):
        self._price_cache.pop(ticker, None)


class TestMarketDataInterfaceMethods:
    @pytest.fixture
    def provider(self):
        return _Minimal()

    def test_initial_state_not_running(self, provider):
        assert provider.is_running is False

    def test_get_price_returns_none_for_unknown(self, provider):
        assert provider.get_price("UNKNOWN") is None

    def test_get_all_prices_empty_initially(self, provider):
        assert provider.get_all_prices() == {}

    async def test_start_sets_running(self, provider):
        await provider.start([])
        assert provider.is_running is True

    async def test_stop_clears_running(self, provider):
        await provider.start([])
        await provider.stop()
        assert provider.is_running is False

    async def test_add_ticker_populates_cache(self, provider):
        await provider.add_ticker("RELIANCE")
        result = provider.get_price("RELIANCE")
        assert result is not None
        assert result.ticker == "RELIANCE"

    async def test_remove_ticker_clears_cache(self, provider):
        await provider.add_ticker("TCS")
        await provider.remove_ticker("TCS")
        assert provider.get_price("TCS") is None

    async def test_get_all_prices_returns_copy(self, provider):
        await provider.add_ticker("INFY")
        prices = provider.get_all_prices()
        # Mutating the returned dict must not affect the internal cache
        prices["NEW"] = PriceData("NEW", 1.0, 1.0, "ts", "unchanged")
        assert provider.get_price("NEW") is None

    async def test_start_with_multiple_tickers(self, provider):
        await provider.start(["RELIANCE", "TCS", "INFY"])
        all_prices = provider.get_all_prices()
        assert set(all_prices.keys()) == {"RELIANCE", "TCS", "INFY"}
