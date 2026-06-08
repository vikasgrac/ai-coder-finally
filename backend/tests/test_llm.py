"""Tests for LLM client and context builders."""
import os
import pytest
from unittest.mock import patch

from app.llm.client import LLMResponse, call_llm, TradeAction, WatchlistChange
from app.llm.context import build_context_block, build_messages

_SAMPLE_PORTFOLIO = {
    "cash": 95000.0,
    "total_value": 108000.0,
    "positions": [
        {
            "ticker": "RELIANCE",
            "quantity": 10,
            "avg_cost": 1300.0,
            "current_price": 1300.0,
            "unrealized_pnl": 0.0,
            "pct_change": 0.0,
        }
    ],
    "watchlist": [
        {"ticker": "RELIANCE", "price": 1300.0},
        {"ticker": "TCS", "price": 2200.0},
    ],
}


class TestLLMClientMockMode:
    async def test_mock_mode_returns_response(self):
        with patch.dict(os.environ, {"LLM_MOCK": "true"}):
            result = await call_llm([{"role": "user", "content": "hello"}])
        assert isinstance(result, LLMResponse)

    async def test_mock_response_has_message(self):
        with patch.dict(os.environ, {"LLM_MOCK": "true"}):
            result = await call_llm([{"role": "user", "content": "hello"}])
        assert isinstance(result.message, str)
        assert len(result.message) > 0

    async def test_mock_response_trades_is_list(self):
        with patch.dict(os.environ, {"LLM_MOCK": "true"}):
            result = await call_llm([])
        assert isinstance(result.trades, list)

    async def test_mock_response_watchlist_changes_is_list(self):
        with patch.dict(os.environ, {"LLM_MOCK": "true"}):
            result = await call_llm([])
        assert isinstance(result.watchlist_changes, list)


class TestLLMResponseParsing:
    def test_parses_full_schema(self):
        raw = '{"message": "test", "trades": [{"ticker": "TCS", "side": "buy", "quantity": 5}], "watchlist_changes": [{"ticker": "INFY", "action": "add"}]}'
        result = LLMResponse.model_validate_json(raw)
        assert result.message == "test"
        assert len(result.trades) == 1
        assert result.trades[0].ticker == "TCS"
        assert len(result.watchlist_changes) == 1

    def test_parses_missing_trades(self):
        raw = '{"message": "hello"}'
        result = LLMResponse.model_validate_json(raw)
        assert result.trades == []
        assert result.watchlist_changes == []

    def test_parses_missing_watchlist_changes(self):
        raw = '{"message": "hello", "trades": []}'
        result = LLMResponse.model_validate_json(raw)
        assert result.watchlist_changes == []

    def test_parses_empty_arrays(self):
        raw = '{"message": "done", "trades": [], "watchlist_changes": []}'
        result = LLMResponse.model_validate_json(raw)
        assert result.message == "done"


class TestContextBuilder:
    def test_context_includes_cash(self):
        text = build_context_block(_SAMPLE_PORTFOLIO)
        assert "95,000.00" in text or "95000" in text

    def test_context_includes_ticker(self):
        text = build_context_block(_SAMPLE_PORTFOLIO)
        assert "RELIANCE" in text

    def test_context_includes_watchlist(self):
        text = build_context_block(_SAMPLE_PORTFOLIO)
        assert "TCS" in text

    def test_build_messages_includes_system(self):
        msgs = build_messages(_SAMPLE_PORTFOLIO, [], "hello")
        assert msgs[0]["role"] == "system"

    def test_build_messages_includes_user_message(self):
        msgs = build_messages(_SAMPLE_PORTFOLIO, [], "hello")
        assert msgs[-1]["role"] == "user"
        assert msgs[-1]["content"] == "hello"

    def test_build_messages_includes_history(self):
        history = [
            {"role": "user", "content": "buy TCS"},
            {"role": "assistant", "content": "Bought 1 TCS"},
        ]
        msgs = build_messages(_SAMPLE_PORTFOLIO, history, "check portfolio")
        roles = [m["role"] for m in msgs]
        assert "user" in roles
        assert "assistant" in roles
