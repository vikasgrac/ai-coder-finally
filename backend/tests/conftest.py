"""Shared test fixtures for the FastAPI app."""
import pytest
from httpx import AsyncClient, ASGITransport

from app import database
from app.database import init_db
from app.main import app


@pytest.fixture
async def test_db(tmp_path):
    """Configure a temp database, initialize schema+seed, reset after test."""
    db_path = tmp_path / "test_finally.db"
    database.set_db_path(db_path)
    await init_db(db_path)
    yield db_path
    database.set_db_path(None)


@pytest.fixture
async def client(test_db):
    """HTTP client wired to the FastAPI app with a pre-initialized temp database."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
