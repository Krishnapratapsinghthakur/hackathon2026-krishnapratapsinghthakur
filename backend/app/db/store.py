"""Data access layer — Redis cache → Postgres → in-memory fallback.

Production cache-aside pattern:
  READ:  Redis cache → miss → Postgres → populate cache → return
  WRITE: Postgres first → invalidate cache

This module is the single source of truth for domain data access.
The rest of the app imports from here, never directly from postgres.py or cache.py.
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from app.core import cache
from app.db import postgres as pg

logger = logging.getLogger(__name__)

_SEED_DIR = Path(__file__).parent / "seed"

# ── In-memory fallback (only used when both Redis and DB are down) ──
_customers: dict[str, dict[str, Any]] = {}
_customers_by_email: dict[str, dict[str, Any]] = {}
_orders: dict[str, dict[str, Any]] = {}
_products: dict[str, dict[str, Any]] = {}
_tickets: list[dict[str, Any]] = []
_knowledge_base: str = ""

_lock = asyncio.Lock()
_loaded = False


def _load_json(filename: str) -> Any:
    with open(_SEED_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def _load_markdown(filename: str) -> str:
    with open(_SEED_DIR / filename, encoding="utf-8") as f:
        return f.read()


async def ensure_loaded() -> None:
    global _loaded
    if _loaded:
        return
    async with _lock:
        if _loaded:
            return
        loop = asyncio.get_event_loop()

        raw_customers = await loop.run_in_executor(None, _load_json, "customers.json")
        for c in raw_customers:
            _customers[c["customer_id"]] = c
            _customers_by_email[c["email"]] = c

        raw_orders = await loop.run_in_executor(None, _load_json, "orders.json")
        for o in raw_orders:
            _orders[o["order_id"]] = o

        raw_products = await loop.run_in_executor(None, _load_json, "products.json")
        for p in raw_products:
            _products[p["product_id"]] = p

        raw_tickets = await loop.run_in_executor(None, _load_json, "tickets.json")
        _tickets.extend(raw_tickets)

        global _knowledge_base
        _knowledge_base = await loop.run_in_executor(
            None, _load_markdown, "knowledge-base.md"
        )

        _loaded = True
        logger.info(
            "Fallback seed data loaded: %d customers, %d orders, %d products, %d tickets",
            len(_customers), len(_orders), len(_products), len(_tickets),
        )


# ═══════════════════════════════════════════════════════════════
# Read operations — Redis → Postgres → in-memory
# ═══════════════════════════════════════════════════════════════

async def get_customer_by_email(email: str) -> dict[str, Any] | None:
    # L1: Redis
    cached = await cache.get_cached_customer_by_email(email)
    if cached is not None:
        return cached

    # L2: Postgres
    if pg.is_connected():
        data = await pg.db_get_customer_by_email(email)
        if data is not None:
            await cache.set_cached_customer_by_email(email, data)
            return data
        return None

    # L3: In-memory fallback
    await ensure_loaded()
    data = _customers_by_email.get(email.lower().strip())
    if data:
        await cache.set_cached_customer_by_email(email, data)
    return data


async def get_customer_by_id(customer_id: str) -> dict[str, Any] | None:
    cached = await cache.get_cached_customer_by_id(customer_id)
    if cached is not None:
        return cached

    if pg.is_connected():
        data = await pg.db_get_customer_by_id(customer_id)
        if data is not None:
            await cache.set_cached_customer_by_id(customer_id, data)
            return data
        return None

    await ensure_loaded()
    data = _customers.get(customer_id)
    if data:
        await cache.set_cached_customer_by_id(customer_id, data)
    return data


async def get_order(order_id: str) -> dict[str, Any] | None:
    cached = await cache.get_cached_order(order_id)
    if cached is not None:
        return cached

    if pg.is_connected():
        data = await pg.db_get_order(order_id)
        if data is not None:
            await cache.set_cached_order(order_id, data)
            return data
        return None

    await ensure_loaded()
    data = _orders.get(order_id)
    if data:
        await cache.set_cached_order(order_id, data)
    return data


async def get_orders_by_customer(customer_id: str) -> list[dict[str, Any]]:
    cached = await cache.get_cached_orders_by_customer(customer_id)
    if cached is not None:
        return cached

    if pg.is_connected():
        data = await pg.db_get_orders_by_customer(customer_id)
        if data:
            await cache.set_cached_orders_by_customer(customer_id, data)
        return data

    await ensure_loaded()
    data = [o for o in _orders.values() if o["customer_id"] == customer_id]
    if data:
        await cache.set_cached_orders_by_customer(customer_id, data)
    return data


async def get_product(product_id: str) -> dict[str, Any] | None:
    cached = await cache.get_cached_product(product_id)
    if cached is not None:
        return cached

    if pg.is_connected():
        data = await pg.db_get_product(product_id)
        if data is not None:
            await cache.set_cached_product(product_id, data)
            return data
        return None

    await ensure_loaded()
    data = _products.get(product_id)
    if data:
        await cache.set_cached_product(product_id, data)
    return data


async def get_knowledge_base() -> str:
    cached = await cache.get_cached_kb()
    if cached is not None:
        return cached

    if pg.is_connected():
        content = await pg.db_get_knowledge_base()
        if content:
            await cache.set_cached_kb(content)
            return content

    await ensure_loaded()
    if _knowledge_base:
        await cache.set_cached_kb(_knowledge_base)
    return _knowledge_base


async def get_all_tickets() -> list[dict[str, Any]]:
    if pg.is_connected():
        return await pg.db_get_all_tickets()
    await ensure_loaded()
    return list(_tickets)


# ═══════════════════════════════════════════════════════════════
# Write operations — Postgres → invalidate cache
# ═══════════════════════════════════════════════════════════════

async def update_order(order_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    if pg.is_connected():
        result = await pg.db_update_order(order_id, updates)
        if result:
            await cache.invalidate_order(order_id)
            cid = result.get("customer_id")
            if cid:
                await cache.invalidate_customer_orders(cid)
        return result

    await ensure_loaded()
    order = _orders.get(order_id)
    if order is None:
        return None
    order.update(updates)
    await cache.invalidate_order(order_id)
    return order
