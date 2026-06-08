"""FastAPI application entry point."""
import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.database import init_db, get_db
from app.market_data import create_market_data_provider
from app.routes import watchlist, stream, portfolio, chat, stock
from app.tasks.snapshot import run_snapshot_loop

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", "..", ".env"))

# Module-level provider instance shared across request handlers
market_provider = None
_snapshot_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global market_provider, _snapshot_task

    await init_db()

    tickers: list[str] = []
    async for conn in get_db():
        async with conn.execute(
            "SELECT ticker FROM watchlist WHERE user_id = 'default' ORDER BY added_at"
        ) as cursor:
            rows = await cursor.fetchall()
            tickers = [row["ticker"] for row in rows]

    market_provider = create_market_data_provider()
    await market_provider.start(tickers)

    _snapshot_task = asyncio.create_task(run_snapshot_loop())

    yield

    _snapshot_task.cancel()
    try:
        await _snapshot_task
    except asyncio.CancelledError:
        pass

    if market_provider is not None:
        await market_provider.stop()


app = FastAPI(title="FinAlly Backend", lifespan=lifespan)

app.include_router(watchlist.router)
app.include_router(stream.router)
app.include_router(portfolio.router)
app.include_router(chat.router)
app.include_router(stock.router)


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Serve frontend static files (set by Dockerfile, optional for local dev)
_static_dir = Path(os.getenv("STATIC_DIR", "/app/static"))
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=str(_static_dir), html=True), name="static")
