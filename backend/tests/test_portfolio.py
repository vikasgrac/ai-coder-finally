"""Tests for the portfolio and trade endpoints."""
import pytest

import app.main as app_state
from app.market_data.interface import MarketDataInterface, PriceData
from app.market_data.simulator import MarketSimulator


class MockProvider(MarketDataInterface):
    """Fixed-price provider for deterministic tests."""

    def __init__(self, prices: dict[str, float]):
        super().__init__()
        for ticker, price in prices.items():
            self._price_cache[ticker] = PriceData(
                ticker=ticker,
                price=price,
                previous_price=price,
                timestamp="2026-01-01T00:00:00+00:00",
                change_direction="unchanged",
            )

    async def start(self, tickers):
        self._running = True

    async def stop(self):
        self._running = False

    async def add_ticker(self, ticker: str):
        if ticker not in self._price_cache:
            self._price_cache[ticker] = PriceData(
                ticker=ticker,
                price=100.0,
                previous_price=100.0,
                timestamp="2026-01-01T00:00:00+00:00",
                change_direction="unchanged",
            )

    async def remove_ticker(self, ticker: str):
        self._price_cache.pop(ticker, None)


PRICES = {
    "RELIANCE": 1300.0,
    "TCS": 2200.0,
    "INFY": 1200.0,
}


@pytest.fixture(autouse=True)
async def mock_provider():
    """Inject a fixed-price mock provider before each test."""
    provider = MockProvider(PRICES)
    app_state.market_provider = provider
    yield provider
    app_state.market_provider = None


class TestGetPortfolio:
    async def test_fresh_portfolio_has_full_cash(self, client):
        response = await client.get("/api/portfolio")
        assert response.status_code == 200
        data = response.json()
        assert data["cash"] == 100000.0

    async def test_fresh_portfolio_has_no_positions(self, client):
        response = await client.get("/api/portfolio")
        assert response.json()["positions"] == []

    async def test_total_value_equals_cash_when_no_positions(self, client):
        response = await client.get("/api/portfolio")
        data = response.json()
        assert data["total_value"] == data["cash"]


class TestBuyTrade:
    async def test_buy_reduces_cash(self, client):
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "buy", "quantity": 10})
        response = await client.get("/api/portfolio")
        data = response.json()
        expected_cash = 100000.0 - 10 * PRICES["RELIANCE"]
        assert abs(data["cash"] - expected_cash) < 0.01

    async def test_buy_creates_position(self, client):
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "buy", "quantity": 10})
        response = await client.get("/api/portfolio")
        positions = response.json()["positions"]
        assert any(p["ticker"] == "RELIANCE" for p in positions)

    async def test_buy_sets_correct_avg_cost(self, client):
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "buy", "quantity": 10})
        response = await client.get("/api/portfolio")
        pos = next(p for p in response.json()["positions"] if p["ticker"] == "RELIANCE")
        assert abs(pos["avg_cost"] - PRICES["RELIANCE"]) < 0.01

    async def test_buy_more_recalculates_avg_cost(self, client):
        # First buy at 1300
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "buy", "quantity": 10})
        # Change price in mock for second buy
        app_state.market_provider._price_cache["RELIANCE"] = PriceData(
            ticker="RELIANCE", price=1500.0, previous_price=1300.0,
            timestamp="2026-01-01T00:00:00+00:00", change_direction="up"
        )
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "buy", "quantity": 10})
        response = await client.get("/api/portfolio")
        pos = next(p for p in response.json()["positions"] if p["ticker"] == "RELIANCE")
        expected_avg = (10 * 1300.0 + 10 * 1500.0) / 20
        assert abs(pos["avg_cost"] - expected_avg) < 0.01

    async def test_buy_insufficient_cash_returns_400(self, client):
        response = await client.post(
            "/api/portfolio/trade",
            json={"ticker": "RELIANCE", "side": "buy", "quantity": 100000},
        )
        assert response.status_code == 400

    async def test_trade_returns_200(self, client):
        response = await client.post(
            "/api/portfolio/trade",
            json={"ticker": "RELIANCE", "side": "buy", "quantity": 1},
        )
        assert response.status_code == 200


class TestSellTrade:
    async def test_sell_increases_cash(self, client):
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "buy", "quantity": 10})
        cash_after_buy = (await client.get("/api/portfolio")).json()["cash"]
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "sell", "quantity": 5})
        cash_after_sell = (await client.get("/api/portfolio")).json()["cash"]
        assert cash_after_sell > cash_after_buy

    async def test_sell_reduces_position_quantity(self, client):
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "buy", "quantity": 10})
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "sell", "quantity": 5})
        response = await client.get("/api/portfolio")
        pos = next(p for p in response.json()["positions"] if p["ticker"] == "RELIANCE")
        assert abs(pos["quantity"] - 5.0) < 1e-6

    async def test_sell_all_removes_position(self, client):
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "buy", "quantity": 10})
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "sell", "quantity": 10})
        response = await client.get("/api/portfolio")
        assert not any(p["ticker"] == "RELIANCE" for p in response.json()["positions"])

    async def test_sell_more_than_held_returns_400(self, client):
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "buy", "quantity": 5})
        response = await client.post(
            "/api/portfolio/trade",
            json={"ticker": "RELIANCE", "side": "sell", "quantity": 10},
        )
        assert response.status_code == 400

    async def test_sell_no_position_returns_400(self, client):
        response = await client.post(
            "/api/portfolio/trade",
            json={"ticker": "RELIANCE", "side": "sell", "quantity": 1},
        )
        assert response.status_code == 400


class TestPortfolioHistory:
    async def test_history_returns_list(self, client):
        response = await client.get("/api/portfolio/history")
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    async def test_history_grows_after_trade(self, client):
        before = len((await client.get("/api/portfolio/history")).json())
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "buy", "quantity": 1})
        after = len((await client.get("/api/portfolio/history")).json())
        assert after > before

    async def test_history_items_have_required_fields(self, client):
        await client.post("/api/portfolio/trade", json={"ticker": "RELIANCE", "side": "buy", "quantity": 1})
        history = (await client.get("/api/portfolio/history")).json()
        for item in history:
            assert "total_value" in item
            assert "recorded_at" in item
