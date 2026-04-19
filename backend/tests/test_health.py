"""Tests for health and settings endpoints."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_health_returns_ok(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "environment" in data
    assert "provider" in data
    assert "database" in data
    assert "cache" in data
    assert "worker" in data


@pytest.mark.asyncio
async def test_health_shows_model_info(client):
    resp = await client.get("/health")
    data = resp.json()
    assert "model_fast" in data
    assert "model_power" in data


@pytest.mark.asyncio
async def test_settings_returns_config(client):
    resp = await client.get("/settings")
    assert resp.status_code == 200
    data = resp.json()
    assert "environment" in data
    assert "resolved_provider" in data
    assert "resolved_models" in data
    assert "smart_routing" in data
    assert "presets" in data


@pytest.mark.asyncio
async def test_settings_models_returns_pricing(client):
    resp = await client.get("/settings/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "pricing_per_1m_tokens" in data
    assert "active" in data


@pytest.mark.asyncio
async def test_settings_costs_empty_initially(client):
    resp = await client.get("/settings/costs")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_tickets"] == 0
    assert data["total_cost_usd"] == 0.0


@pytest.mark.asyncio
async def test_request_id_header_returned(client):
    resp = await client.get("/health")
    assert "X-Request-ID" in resp.headers


@pytest.mark.asyncio
async def test_custom_request_id_echoed(client):
    rid = "test-req-12345"
    resp = await client.get("/health", headers={"X-Request-ID": rid})
    assert resp.headers["X-Request-ID"] == rid
