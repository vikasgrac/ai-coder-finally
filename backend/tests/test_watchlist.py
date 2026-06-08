"""Tests for the watchlist endpoints."""
import pytest

from schema.seed import DEFAULT_WATCHLIST


class TestGetWatchlist:
    async def test_returns_default_tickers(self, client):
        response = await client.get("/api/watchlist")
        assert response.status_code == 200
        tickers = {item["ticker"] for item in response.json()}
        assert tickers == set(DEFAULT_WATCHLIST)

    async def test_each_item_has_required_fields(self, client):
        response = await client.get("/api/watchlist")
        for item in response.json():
            assert "ticker" in item
            assert "price" in item
            assert "previous_price" in item
            assert "change_direction" in item
            assert "timestamp" in item


class TestAddTicker:
    async def test_add_new_ticker_returns_201(self, client):
        response = await client.post("/api/watchlist", json={"ticker": "ONGC"})
        assert response.status_code == 201

    async def test_added_ticker_appears_in_get(self, client):
        await client.post("/api/watchlist", json={"ticker": "ONGC"})
        response = await client.get("/api/watchlist")
        tickers = {item["ticker"] for item in response.json()}
        assert "ONGC" in tickers

    async def test_duplicate_ticker_returns_409(self, client):
        await client.post("/api/watchlist", json={"ticker": "ONGC"})
        response = await client.post("/api/watchlist", json={"ticker": "ONGC"})
        assert response.status_code == 409

    async def test_ticker_is_uppercased(self, client):
        response = await client.post("/api/watchlist", json={"ticker": "ongc"})
        assert response.status_code == 201
        assert response.json()["ticker"] == "ONGC"


class TestRemoveTicker:
    async def test_remove_existing_ticker_returns_200(self, client):
        response = await client.delete("/api/watchlist/RELIANCE")
        assert response.status_code == 200

    async def test_removed_ticker_absent_from_get(self, client):
        await client.delete("/api/watchlist/RELIANCE")
        response = await client.get("/api/watchlist")
        tickers = {item["ticker"] for item in response.json()}
        assert "RELIANCE" not in tickers

    async def test_remove_unknown_ticker_returns_404(self, client):
        response = await client.delete("/api/watchlist/NONEXISTENT")
        assert response.status_code == 404
