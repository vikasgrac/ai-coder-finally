"""Tests for the health endpoint."""
import pytest


class TestHealthEndpoint:
    async def test_health_returns_200(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200

    async def test_health_returns_ok(self, client):
        response = await client.get("/api/health")
        assert response.json() == {"status": "ok"}
