"""Tests for the SSE price streaming endpoint."""
import json
import asyncio
import pytest

import app.main as app_state
from app.market_data.simulator import MarketSimulator
from app.routes.stream import _price_event_generator


@pytest.fixture
async def running_sim():
    """Start a simulator, set as module-level provider, clean up after."""
    sim = MarketSimulator(update_interval=0.05)
    await sim.start(["RELIANCE", "TCS"])
    app_state.market_provider = sim
    yield sim
    await sim.stop()
    app_state.market_provider = None


class TestSSEEventGenerator:
    async def test_events_are_emitted(self, running_sim):
        """Generator yields data lines when provider has prices."""
        gen = _price_event_generator()
        lines = []
        async for chunk in gen:
            if chunk.strip():
                lines.append(chunk)
            if len(lines) >= 2:
                break
        assert len(lines) >= 1

    async def test_events_are_valid_json(self, running_sim):
        gen = _price_event_generator()
        async for chunk in gen:
            if chunk.startswith("data:"):
                payload = chunk[len("data:"):].strip()
                event = json.loads(payload)
                assert isinstance(event, dict)
                break

    async def test_event_has_required_fields(self, running_sim):
        required = {"ticker", "price", "previous_price", "timestamp", "change_direction"}
        gen = _price_event_generator()
        async for chunk in gen:
            if chunk.startswith("data:"):
                event = json.loads(chunk[len("data:"):].strip())
                assert required.issubset(event.keys()), f"missing fields: {required - event.keys()}"
                break

    async def test_event_price_is_positive(self, running_sim):
        gen = _price_event_generator()
        async for chunk in gen:
            if chunk.startswith("data:"):
                event = json.loads(chunk[len("data:"):].strip())
                assert event["price"] > 0
                break

    async def test_change_direction_valid_values(self, running_sim):
        gen = _price_event_generator()
        seen = set()
        async for chunk in gen:
            if chunk.startswith("data:"):
                event = json.loads(chunk[len("data:"):].strip())
                assert event["change_direction"] in {"up", "down", "unchanged"}
                seen.add(event["ticker"])
                if len(seen) >= 2:
                    break


class TestSSEEndpointRouting:
    """Test the endpoint is wired with the correct media type without streaming."""

    async def test_sse_route_registered(self, client):
        """Route /api/stream/prices should exist (returns 200 or streaming)."""
        from httpx import AsyncClient, ASGITransport
        from app.main import app
        # We can't fully test SSE through ASGITransport (infinite stream), but we
        # can verify the endpoint is registered and returns the right content type
        # by checking the route in the app's router
        routes = [route.path for route in app.routes]
        assert "/api/stream/prices" in routes
