"""
Unit tests for TapetidePoller.

The tests do NOT need a real Tapetide API key.  Network calls are avoided by:
  - testing _process_quotes, _apply_micro_moves, _set_price, etc. directly
  - patching fastmcp.Client where async start() is exercised
"""
import asyncio
import pytest
from unittest.mock import MagicMock, patch

from app.market_data.interface import MarketDataInterface, PriceData
from app.market_data.tapetide import TapetidePoller


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_poller(api_key: str = "test-key") -> TapetidePoller:
    return TapetidePoller(api_key=api_key)


def _text_content(text: str):
    """Minimal stand-in for fastmcp TextContent."""
    obj = MagicMock()
    obj.text = text
    return obj


# ---------------------------------------------------------------------------
# Interface compliance
# ---------------------------------------------------------------------------

class TestInterfaceCompliance:
    def test_is_market_data_interface(self):
        assert isinstance(make_poller(), MarketDataInterface)

    def test_has_all_abstract_methods(self):
        p = make_poller()
        for method in ("start", "stop", "add_ticker", "remove_ticker"):
            assert callable(getattr(p, method))

    def test_has_poll_and_micro_constants(self):
        assert TapetidePoller.POLL_INTERVAL > 0
        assert TapetidePoller.MICRO_INTERVAL > 0
        assert TapetidePoller.MICRO_VOLATILITY > 0

    def test_default_mcp_url(self):
        p = make_poller()
        assert "tapetide.com" in p._mcp_url


# ---------------------------------------------------------------------------
# add_ticker / remove_ticker
# ---------------------------------------------------------------------------

class TestTickerManagement:
    async def test_add_ticker_creates_seeded_price_entry(self):
        from app.market_data.simulator import DEFAULT_SEED_PRICE, SEED_PRICES
        p = make_poller()
        await p.add_ticker("RELIANCE")
        pd = p.get_price("RELIANCE")
        assert pd is not None
        assert pd.ticker == "RELIANCE"
        assert pd.price == SEED_PRICES.get("RELIANCE", DEFAULT_SEED_PRICE)

    async def test_add_ticker_is_idempotent(self):
        p = make_poller()
        await p.add_ticker("TCS")
        await p.add_ticker("TCS")
        assert len([t for t in p._tickers if t == "TCS"]) == 1

    async def test_remove_ticker_clears_entry(self):
        p = make_poller()
        await p.add_ticker("INFY")
        await p.remove_ticker("INFY")
        assert p.get_price("INFY") is None

    async def test_remove_unknown_ticker_no_error(self):
        p = make_poller()
        await p.remove_ticker("NONEXISTENT")

    async def test_initial_change_direction_unchanged(self):
        p = make_poller()
        await p.add_ticker("WIPRO")
        assert p.get_price("WIPRO").change_direction == "unchanged"


# ---------------------------------------------------------------------------
# _set_price
# ---------------------------------------------------------------------------

class TestSetPrice:
    async def test_set_price_updates_cache(self):
        p = make_poller()
        await p.add_ticker("RELIANCE")
        p._set_price("RELIANCE", 1350.0, "2026-01-01T00:00:00Z")
        pd = p.get_price("RELIANCE")
        assert pd.price == 1350.0

    async def test_set_price_direction_up(self):
        p = make_poller()
        await p.add_ticker("RELIANCE")
        p._set_price("RELIANCE", 500.0, "ts1")  # seed with low price
        p._set_price("RELIANCE", 600.0, "ts2")
        assert p.get_price("RELIANCE").change_direction == "up"

    async def test_set_price_direction_down(self):
        p = make_poller()
        await p.add_ticker("RELIANCE")
        p._set_price("RELIANCE", 600.0, "ts1")
        p._set_price("RELIANCE", 500.0, "ts2")
        assert p.get_price("RELIANCE").change_direction == "down"

    async def test_set_price_direction_unchanged(self):
        p = make_poller()
        await p.add_ticker("RELIANCE")
        p._set_price("RELIANCE", 1300.0, "ts1")
        p._set_price("RELIANCE", 1300.0, "ts2")
        assert p.get_price("RELIANCE").change_direction == "unchanged"

    async def test_set_price_ignores_unknown_ticker(self):
        p = make_poller()
        p._set_price("UNKNOWNTICKER", 999.0, "ts")
        assert p.get_price("UNKNOWNTICKER") is None

    async def test_set_price_records_previous(self):
        p = make_poller()
        await p.add_ticker("TCS")
        p._set_price("TCS", 2000.0, "ts1")
        p._set_price("TCS", 2100.0, "ts2")
        pd = p.get_price("TCS")
        assert pd.previous_price == 2000.0
        assert pd.price == 2100.0


# ---------------------------------------------------------------------------
# _process_quotes — list format
# ---------------------------------------------------------------------------

class TestProcessQuotesList:
    async def test_list_with_price_field(self):
        p = make_poller()
        await p.add_ticker("RELIANCE")
        await p.add_ticker("TCS")
        p._process_quotes([
            {"ticker": "RELIANCE", "price": 1320.5},
            {"ticker": "TCS",      "price": 2185.0},
        ])
        assert p.get_price("RELIANCE").price == 1320.5
        assert p.get_price("TCS").price == 2185.0

    async def test_list_with_last_price_field(self):
        p = make_poller()
        await p.add_ticker("INFY")
        p._process_quotes([{"ticker": "INFY", "last_price": 1210.0}])
        assert p.get_price("INFY").price == 1210.0

    async def test_list_with_ltp_field(self):
        p = make_poller()
        await p.add_ticker("WIPRO")
        p._process_quotes([{"ticker": "WIPRO", "ltp": 455.0}])
        assert p.get_price("WIPRO").price == 455.0

    async def test_list_with_symbol_field(self):
        p = make_poller()
        await p.add_ticker("SBIN")
        p._process_quotes([{"symbol": "SBIN", "price": 610.0}])
        assert p.get_price("SBIN").price == 610.0

    async def test_list_unknown_ticker_ignored(self):
        p = make_poller()
        await p.add_ticker("RELIANCE")
        seed_price = p.get_price("RELIANCE").price
        p._process_quotes([{"ticker": "UNKNOWN", "price": 999.0}])
        assert p.get_price("RELIANCE").price == seed_price

    async def test_empty_list_no_error(self):
        p = make_poller()
        await p.add_ticker("TCS")
        p._process_quotes([])

    async def test_none_result_no_error(self):
        p = make_poller()
        await p.add_ticker("TCS")
        p._process_quotes(None)


# ---------------------------------------------------------------------------
# _process_quotes — dict format
# ---------------------------------------------------------------------------

class TestProcessQuotesDict:
    async def test_dict_ticker_to_price_object(self):
        p = make_poller()
        await p.add_ticker("RELIANCE")
        await p.add_ticker("TCS")
        p._process_quotes({
            "RELIANCE": {"price": 1310.0},
            "TCS":      {"price": 2195.0},
        })
        assert p.get_price("RELIANCE").price == 1310.0
        assert p.get_price("TCS").price == 2195.0

    async def test_dict_ticker_to_last_price(self):
        p = make_poller()
        await p.add_ticker("HDFCBANK")
        p._process_quotes({"HDFCBANK": {"last_price": 1605.0}})
        assert p.get_price("HDFCBANK").price == 1605.0

    async def test_dict_flat_value(self):
        """{"RELIANCE": 1320.5} — scalar value format."""
        p = make_poller()
        await p.add_ticker("RELIANCE")
        p._process_quotes({"RELIANCE": 1320.5})
        assert p.get_price("RELIANCE").price == 1320.5


# ---------------------------------------------------------------------------
# _process_quotes — FastMCP TextContent wrapper
# ---------------------------------------------------------------------------

class TestProcessQuotesTextContent:
    async def test_text_content_list_json(self):
        import json
        p = make_poller()
        await p.add_ticker("RELIANCE")
        payload = json.dumps([{"ticker": "RELIANCE", "price": 1330.0}])
        p._process_quotes([_text_content(payload)])
        assert p.get_price("RELIANCE").price == 1330.0

    async def test_text_content_dict_json(self):
        import json
        p = make_poller()
        await p.add_ticker("TCS")
        payload = json.dumps({"TCS": {"price": 2210.0}})
        p._process_quotes([_text_content(payload)])
        assert p.get_price("TCS").price == 2210.0

    async def test_invalid_json_in_text_content_no_error(self):
        p = make_poller()
        await p.add_ticker("INFY")
        price_before = p.get_price("INFY").price
        p._process_quotes([_text_content("not json at all")])
        # price must remain unchanged (invalid JSON → no update)
        assert p.get_price("INFY").price == price_before

    async def test_multiple_text_content_uses_first_valid(self):
        import json
        p = make_poller()
        await p.add_ticker("SBIN")
        payload = json.dumps([{"ticker": "SBIN", "price": 615.0}])
        p._process_quotes([
            _text_content("invalid json"),
            _text_content(payload),
        ])
        assert p.get_price("SBIN").price == 615.0


# ---------------------------------------------------------------------------
# _apply_micro_moves
# ---------------------------------------------------------------------------

class TestApplyMicroMoves:
    async def test_micro_moves_change_seeded_price(self):
        p = make_poller()
        await p.add_ticker("RELIANCE")
        p._set_price("RELIANCE", 1300.0, "ts")
        old = p.get_price("RELIANCE").price

        # Run many micro-moves; at least some must differ
        changed = False
        for _ in range(100):
            p._apply_micro_moves()
            if p.get_price("RELIANCE").price != old:
                changed = True
                break

        assert changed, "Micro-moves never changed the price"

    async def test_micro_moves_skip_zero_price(self):
        p = make_poller()
        await p.add_ticker("TCS")
        # Manually zero out the price to exercise the skip-zero guard
        p._price_cache["TCS"] = PriceData(
            ticker="TCS", price=0.0, previous_price=0.0,
            timestamp="ts", change_direction="unchanged",
        )
        p._apply_micro_moves()
        assert p.get_price("TCS").price == 0.0

    async def test_micro_moves_price_stays_positive(self):
        p = make_poller()
        await p.add_ticker("WIPRO")
        p._set_price("WIPRO", 450.0, "ts")
        for _ in range(1000):
            p._apply_micro_moves()
        assert p.get_price("WIPRO").price > 0

    async def test_micro_moves_direction_consistency(self):
        p = make_poller()
        await p.add_ticker("INFY")
        p._set_price("INFY", 1200.0, "ts")
        p._apply_micro_moves()
        pd = p.get_price("INFY")
        if pd.price > pd.previous_price:
            assert pd.change_direction == "up"
        elif pd.price < pd.previous_price:
            assert pd.change_direction == "down"
        else:
            assert pd.change_direction == "unchanged"

    async def test_micro_moves_are_small(self):
        """Each micro-move must be < 1% with the configured low volatility."""
        p = make_poller()
        await p.add_ticker("RELIANCE")
        p._set_price("RELIANCE", 1300.0, "ts")

        for _ in range(200):
            before = p.get_price("RELIANCE").price
            p._apply_micro_moves()
            after  = p.get_price("RELIANCE").price
            if before > 0:
                assert abs(after - before) / before < 0.01, (
                    f"Micro-move too large: {before} → {after}"
                )


# ---------------------------------------------------------------------------
# start() / stop() with mocked FastMCP
# ---------------------------------------------------------------------------

class TestStartStop:
    async def test_start_sets_running(self):
        p = make_poller()
        with patch("app.market_data.tapetide._HAS_FASTMCP", False):
            await p.start(["RELIANCE"])
            assert p.is_running is True
            await p.stop()

    async def test_stop_clears_running(self):
        p = make_poller()
        with patch("app.market_data.tapetide._HAS_FASTMCP", False):
            await p.start(["RELIANCE"])
            await p.stop()
            assert p.is_running is False

    async def test_start_populates_tickers(self):
        p = make_poller()
        with patch("app.market_data.tapetide._HAS_FASTMCP", False):
            await p.start(["RELIANCE", "TCS"])
            assert "RELIANCE" in p._tickers
            assert "TCS" in p._tickers
            await p.stop()

    async def test_stop_after_never_started_no_error(self):
        p = make_poller()
        await p.stop()

    async def test_start_calls_initial_poll(self):
        """start() must call _poll_tapetide immediately (to seed the cache)."""
        p = make_poller()
        called = []

        async def fake_poll():
            called.append(True)

        p._poll_tapetide = fake_poll

        with patch("app.market_data.tapetide._HAS_FASTMCP", False):
            # Patch again so the task's loop doesn't fire real poll
            original_poll_loop = p._poll_loop

            async def noop_poll_loop():
                pass

            p._poll_loop = noop_poll_loop
            await p.start(["RELIANCE"])
            await p.stop()

        assert len(called) >= 1, "_poll_tapetide was not called on start()"

    async def test_missing_fastmcp_logs_error(self, caplog):
        import logging
        p = make_poller()
        await p.add_ticker("RELIANCE")

        with patch("app.market_data.tapetide._HAS_FASTMCP", False):
            with caplog.at_level(logging.ERROR, logger="app.market_data.tapetide"):
                await p._poll_tapetide()

        assert any("fastmcp" in m.lower() for m in caplog.messages)
