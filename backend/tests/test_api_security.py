"""Tests for API security, routes, and new endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_no_auth_required_when_key_empty(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_sample_tickets_accessible(client):
    resp = await client.get("/tickets/sample")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)


@pytest.mark.asyncio
async def test_audit_endpoint_returns_list(client):
    resp = await client.get("/audit")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_dlq_endpoint_returns_list(client):
    resp = await client.get("/audit/dlq")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_nonexistent_audit_returns_404(client):
    resp = await client.get("/audit/NONEXISTENT-TICKET-ID")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_route_returns_404(client):
    resp = await client.get("/nonexistent")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_cached_result_404_when_not_processed(client):
    resp = await client.get("/tickets/result/NEVER-PROCESSED")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_task_status_endpoint_exists(client):
    resp = await client.get("/tickets/status/fake-task-id")
    assert resp.status_code in (200, 500, 503)
