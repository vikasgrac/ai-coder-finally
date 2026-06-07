"""Unit tests for the create_market_data_provider factory function."""
import pytest
from unittest.mock import patch

from app.market_data import create_market_data_provider
from app.market_data.simulator import MarketSimulator
from app.market_data.tapetide import TapetidePoller


class TestCreateMarketDataProvider:
    def test_no_key_returns_simulator(self):
        with patch.dict("os.environ", {}, clear=False):
            # Ensure the variable is absent
            import os
            os.environ.pop("TAPETIDE_API_KEY", None)
            provider = create_market_data_provider()
        assert isinstance(provider, MarketSimulator)

    def test_empty_key_returns_simulator(self):
        with patch.dict("os.environ", {"TAPETIDE_API_KEY": ""}):
            provider = create_market_data_provider()
        assert isinstance(provider, MarketSimulator)

    def test_whitespace_key_returns_simulator(self):
        with patch.dict("os.environ", {"TAPETIDE_API_KEY": "   "}):
            provider = create_market_data_provider()
        assert isinstance(provider, MarketSimulator)

    def test_key_returns_tapetide(self):
        with patch.dict("os.environ", {"TAPETIDE_API_KEY": "real-api-key"}):
            provider = create_market_data_provider()
        assert isinstance(provider, TapetidePoller)

    def test_tapetide_receives_api_key(self):
        with patch.dict("os.environ", {"TAPETIDE_API_KEY": "my-secret-key"}):
            provider = create_market_data_provider()
        assert isinstance(provider, TapetidePoller)
        assert provider._api_key == "my-secret-key"
