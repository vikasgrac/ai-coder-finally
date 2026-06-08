"""Tests for the /api/chat endpoint (all with LLM_MOCK=true)."""
import os
import pytest
import aiosqlite
from unittest.mock import patch

import app.main as app_state
from tests.test_portfolio import MockProvider, PRICES


@pytest.fixture(autouse=True)
def mock_llm_mode():
    with patch.dict(os.environ, {"LLM_MOCK": "true"}):
        yield


@pytest.fixture(autouse=True)
async def mock_provider():
    provider = MockProvider(PRICES)
    app_state.market_provider = provider
    yield provider
    app_state.market_provider = None


class TestChatEndpoint:
    async def test_chat_returns_200(self, client):
        response = await client.post("/api/chat", json={"message": "hello"})
        assert response.status_code == 200

    async def test_chat_response_has_message(self, client):
        response = await client.post("/api/chat", json={"message": "hello"})
        data = response.json()
        assert "message" in data
        assert isinstance(data["message"], str)

    async def test_chat_response_has_actions(self, client):
        response = await client.post("/api/chat", json={"message": "hello"})
        data = response.json()
        assert "actions" in data
        assert "trades" in data["actions"]
        assert "watchlist_changes" in data["actions"]

    async def test_user_message_persisted(self, client, test_db):
        await client.post("/api/chat", json={"message": "test message"})
        async with aiosqlite.connect(test_db) as conn:
            async with conn.execute(
                "SELECT content FROM chat_messages WHERE role = 'user'"
            ) as cur:
                rows = await cur.fetchall()
        assert any("test message" in r[0] for r in rows)

    async def test_assistant_response_persisted(self, client, test_db):
        await client.post("/api/chat", json={"message": "hello"})
        async with aiosqlite.connect(test_db) as conn:
            async with conn.execute(
                "SELECT content FROM chat_messages WHERE role = 'assistant'"
            ) as cur:
                rows = await cur.fetchall()
        assert len(rows) >= 1

    async def test_mock_trade_auto_executed(self, client):
        """Mock LLM buys 1 RELIANCE — position should appear."""
        await client.post("/api/chat", json={"message": "buy something"})
        portfolio = (await client.get("/api/portfolio")).json()
        tickers = [p["ticker"] for p in portfolio["positions"]]
        assert "RELIANCE" in tickers

    async def test_multi_turn_context(self, client):
        """Second message should see conversation history."""
        await client.post("/api/chat", json={"message": "first message"})
        response = await client.post("/api/chat", json={"message": "second message"})
        assert response.status_code == 200

    async def test_empty_message_returns_422(self, client):
        response = await client.post("/api/chat", json={"message": ""})
        assert response.status_code == 422

    async def test_actions_stored_as_json_in_db(self, client, test_db):
        """Assistant's actions column should be valid JSON."""
        import json
        await client.post("/api/chat", json={"message": "hello"})
        async with aiosqlite.connect(test_db) as conn:
            async with conn.execute(
                "SELECT actions FROM chat_messages WHERE role = 'assistant'"
            ) as cur:
                rows = await cur.fetchall()
        for row in rows:
            if row[0] is not None:
                parsed = json.loads(row[0])
                assert "trades" in parsed
                assert "watchlist_changes" in parsed
