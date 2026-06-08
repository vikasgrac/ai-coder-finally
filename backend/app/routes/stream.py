"""SSE price streaming endpoint."""
import asyncio
import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

import app.main as app_state

router = APIRouter(prefix="/api/stream", tags=["stream"])

_SSE_INTERVAL = 0.5  # seconds between event pushes


async def _price_event_generator():
    while True:
        provider = app_state.market_provider
        if provider is not None:
            prices = provider.get_all_prices()
            for ticker, pd in prices.items():
                data = {
                    "ticker": pd.ticker,
                    "price": pd.price,
                    "previous_price": pd.previous_price,
                    "timestamp": pd.timestamp,
                    "change_direction": pd.change_direction,
                }
                yield f"data: {json.dumps(data)}\n\n"
        await asyncio.sleep(_SSE_INTERVAL)


@router.get("/prices")
async def stream_prices():
    return StreamingResponse(
        _price_event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
