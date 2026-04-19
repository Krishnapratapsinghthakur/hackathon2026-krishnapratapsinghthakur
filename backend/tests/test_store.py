"""Tests for data store access layer."""

from __future__ import annotations

import pytest

from app.db.store import (
    ensure_loaded,
    get_customer_by_email,
    get_customer_by_id,
    get_order,
    get_orders_by_customer,
    get_product,
    get_knowledge_base,
    get_all_tickets,
)


@pytest.fixture(autouse=True)
async def load_store():
    await ensure_loaded()


@pytest.mark.asyncio
async def test_get_customer_by_email():
    customer = await get_customer_by_email("alice.turner@email.com")
    assert customer is not None
    assert customer["customer_id"] == "C001"
    assert customer["name"] == "Alice Turner"
    assert customer["tier"] == "vip"


@pytest.mark.asyncio
async def test_get_customer_by_email_not_found():
    customer = await get_customer_by_email("nobody@nowhere.com")
    assert customer is None


@pytest.mark.asyncio
async def test_get_customer_by_id():
    customer = await get_customer_by_id("C001")
    assert customer is not None
    assert customer["email"] == "alice.turner@email.com"


@pytest.mark.asyncio
async def test_get_order():
    order = await get_order("ORD-1001")
    assert order is not None
    assert order["customer_id"] == "C001"
    assert order["status"] == "delivered"
    assert order["amount"] == 129.99


@pytest.mark.asyncio
async def test_get_order_not_found():
    order = await get_order("ORD-9999")
    assert order is None


@pytest.mark.asyncio
async def test_get_orders_by_customer():
    orders = await get_orders_by_customer("C001")
    assert len(orders) >= 1
    assert all(o["customer_id"] == "C001" for o in orders)


@pytest.mark.asyncio
async def test_get_product():
    product = await get_product("P001")
    assert product is not None
    assert product["name"] == "ProSound Wireless Headphones"
    assert product["warranty_months"] == 12


@pytest.mark.asyncio
async def test_get_product_not_found():
    product = await get_product("P999")
    assert product is None


@pytest.mark.asyncio
async def test_get_knowledge_base():
    kb = await get_knowledge_base()
    assert len(kb) > 100
    assert "Return Policy" in kb
    assert "Refund Policy" in kb


@pytest.mark.asyncio
async def test_get_all_tickets():
    tickets = await get_all_tickets()
    assert len(tickets) == 20
    assert all("ticket_id" in t for t in tickets)
