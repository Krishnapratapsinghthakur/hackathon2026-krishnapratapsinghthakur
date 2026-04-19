"""Shared test fixtures."""

from __future__ import annotations

import os
import pytest
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("DATABASE_URL", "")
os.environ.setdefault("API_KEY", "")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("GROQ_API_KEY", "test-key")
os.environ.setdefault("MOCK_TOOL_FAILURE_RATE", "0")

from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def sample_ticket():
    return {
        "ticket_id": "TKT-TEST-001",
        "customer_email": "alice.turner@email.com",
        "subject": "Test refund request",
        "body": "I want a refund for order ORD-1001. The headphones stopped working.",
        "source": "email",
        "tier": 1,
    }


@pytest.fixture
def invalid_ticket():
    return {
        "ticket_id": "",
        "customer_email": "not-an-email",
        "subject": "",
        "body": "",
    }
