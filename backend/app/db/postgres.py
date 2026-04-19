"""Async Postgres layer — schema, seeding, and all CRUD via Supabase.

Production pattern:
- Connection pool lifecycle (startup/shutdown)
- Auto-create ALL tables on first connect (domain + operational)
- Idempotent seed: loads JSON fixtures on first run, skips if data exists
- All CRUD for domain data (customers, orders, products, tickets, knowledge_base)
  and operational data (audit, cost tracking, DLQ)

If DATABASE_URL is not set, the app falls back to in-memory.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import asyncpg

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_pool: asyncpg.Pool | None = None
_SEED_DIR = Path(__file__).parent / "seed"

# ═══════════════════════════════════════════════════════════════
# Schema
# ═══════════════════════════════════════════════════════════════

SCHEMA_SQL = """
-- ── Domain tables ────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS customers (
    customer_id     TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    email           TEXT NOT NULL UNIQUE,
    phone           TEXT,
    tier            TEXT NOT NULL DEFAULT 'standard',
    member_since    TEXT,
    total_orders    INTEGER DEFAULT 0,
    total_spent     REAL DEFAULT 0.0,
    address         JSONB DEFAULT '{}'::jsonb,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS products (
    product_id          TEXT PRIMARY KEY,
    name                TEXT NOT NULL,
    category            TEXT,
    price               REAL NOT NULL,
    warranty_months     INTEGER DEFAULT 0,
    return_window_days  INTEGER DEFAULT 30,
    returnable          BOOLEAN DEFAULT true,
    notes               TEXT
);

CREATE TABLE IF NOT EXISTS orders (
    order_id        TEXT PRIMARY KEY,
    customer_id     TEXT NOT NULL REFERENCES customers(customer_id),
    product_id      TEXT NOT NULL REFERENCES products(product_id),
    quantity        INTEGER DEFAULT 1,
    amount          REAL NOT NULL,
    status          TEXT NOT NULL DEFAULT 'processing',
    order_date      TEXT,
    delivery_date   TEXT,
    return_deadline TEXT,
    refund_status   TEXT,
    notes           TEXT
);

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id       TEXT PRIMARY KEY,
    customer_email  TEXT NOT NULL,
    subject         TEXT NOT NULL,
    body            TEXT NOT NULL,
    source          TEXT DEFAULT 'email',
    created_at      TIMESTAMPTZ,
    tier            INTEGER DEFAULT 1,
    expected_action TEXT
);

CREATE TABLE IF NOT EXISTS knowledge_base (
    id              SERIAL PRIMARY KEY,
    content         TEXT NOT NULL,
    updated_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Operational tables ───────────────────────────────────────

CREATE TABLE IF NOT EXISTS ticket_audit (
    id              SERIAL PRIMARY KEY,
    ticket_id       TEXT NOT NULL UNIQUE,
    status          TEXT NOT NULL DEFAULT 'queued',
    category        TEXT,
    priority        TEXT,
    confidence      REAL,
    tool_calls      JSONB DEFAULT '[]'::jsonb,
    reasoning       JSONB DEFAULT '[]'::jsonb,
    final_response  TEXT,
    escalation_summary TEXT,
    error           TEXT,
    started_at      TIMESTAMPTZ DEFAULT now(),
    completed_at    TIMESTAMPTZ,
    retries         INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cost_tracking (
    id              SERIAL PRIMARY KEY,
    ticket_id       TEXT NOT NULL,
    model_used      TEXT NOT NULL,
    model_tier      TEXT NOT NULL,
    input_tokens    INTEGER DEFAULT 0,
    output_tokens   INTEGER DEFAULT 0,
    estimated_cost  REAL DEFAULT 0.0,
    llm_calls       INTEGER DEFAULT 0,
    tool_calls      INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id              SERIAL PRIMARY KEY,
    ticket_id       TEXT NOT NULL,
    error           TEXT,
    retries         INTEGER DEFAULT 0,
    created_at      TIMESTAMPTZ DEFAULT now()
);

-- ── Indexes ──────────────────────────────────────────────────

CREATE INDEX IF NOT EXISTS idx_customers_email ON customers(email);
CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders(customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_product ON orders(product_id);
CREATE INDEX IF NOT EXISTS idx_tickets_email ON tickets(customer_email);
CREATE INDEX IF NOT EXISTS idx_audit_ticket_id ON ticket_audit(ticket_id);
CREATE INDEX IF NOT EXISTS idx_cost_ticket_id ON cost_tracking(ticket_id);
CREATE INDEX IF NOT EXISTS idx_dlq_ticket_id ON dead_letter_queue(ticket_id);
"""


# ═══════════════════════════════════════════════════════════════
# Lifecycle
# ═══════════════════════════════════════════════════════════════

async def init_db() -> bool:
    global _pool
    settings = get_settings()

    if not settings.database_url:
        logger.warning("DATABASE_URL not set — running in-memory only (data lost on restart)")
        return False

    try:
        _pool = await asyncpg.create_pool(
            dsn=settings.database_url,
            min_size=2,
            max_size=10,
            command_timeout=30,
        )
        async with _pool.acquire() as conn:
            await conn.execute(SCHEMA_SQL)

        await _seed_if_empty()
        logger.info("Postgres connected, schema ready, data seeded")
        return True
    except Exception as e:
        logger.error("Postgres connection failed: %s — falling back to in-memory", e)
        _pool = None
        return False


async def close_db() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None
        logger.info("Postgres connection pool closed")


def is_connected() -> bool:
    return _pool is not None


# ═══════════════════════════════════════════════════════════════
# Seed (idempotent — only inserts if tables are empty)
# ═══════════════════════════════════════════════════════════════

def _load_json(filename: str) -> Any:
    with open(_SEED_DIR / filename, encoding="utf-8") as f:
        return json.load(f)


def _load_text(filename: str) -> str:
    with open(_SEED_DIR / filename, encoding="utf-8") as f:
        return f.read()


async def _seed_if_empty() -> None:
    if not _pool:
        return

    async with _pool.acquire() as conn:
        count = await conn.fetchval("SELECT count(*) FROM customers")
        if count > 0:
            logger.info("Database already seeded (%d customers). Skipping.", count)
            return

    logger.info("Seeding database from JSON fixtures...")

    customers = _load_json("customers.json")
    products = _load_json("products.json")
    orders = _load_json("orders.json")
    tickets = _load_json("tickets.json")
    kb_content = _load_text("knowledge-base.md")

    async with _pool.acquire() as conn:
        async with conn.transaction():
            for c in customers:
                await conn.execute(
                    """INSERT INTO customers
                       (customer_id, name, email, phone, tier, member_since,
                        total_orders, total_spent, address, notes)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9::jsonb,$10)
                       ON CONFLICT (customer_id) DO NOTHING""",
                    c["customer_id"], c["name"], c["email"], c.get("phone"),
                    c["tier"], c.get("member_since"),
                    c.get("total_orders", 0), c.get("total_spent", 0.0),
                    json.dumps(c.get("address", {})),
                    c.get("notes"),
                )

            for p in products:
                await conn.execute(
                    """INSERT INTO products
                       (product_id, name, category, price, warranty_months,
                        return_window_days, returnable, notes)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                       ON CONFLICT (product_id) DO NOTHING""",
                    p["product_id"], p["name"], p.get("category"),
                    p["price"], p.get("warranty_months", 0),
                    p.get("return_window_days", 30), p.get("returnable", True),
                    p.get("notes"),
                )

            for o in orders:
                await conn.execute(
                    """INSERT INTO orders
                       (order_id, customer_id, product_id, quantity, amount,
                        status, order_date, delivery_date, return_deadline,
                        refund_status, notes)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11)
                       ON CONFLICT (order_id) DO NOTHING""",
                    o["order_id"], o["customer_id"], o["product_id"],
                    o.get("quantity", 1), o["amount"],
                    o["status"], o.get("order_date"), o.get("delivery_date"),
                    o.get("return_deadline"), o.get("refund_status"),
                    o.get("notes"),
                )

            for t in tickets:
                created_at = None
                if t.get("created_at"):
                    from datetime import datetime as dt
                    try:
                        created_at = dt.fromisoformat(t["created_at"].replace("Z", "+00:00"))
                    except (ValueError, AttributeError):
                        pass
                await conn.execute(
                    """INSERT INTO tickets
                       (ticket_id, customer_email, subject, body, source,
                        created_at, tier, expected_action)
                       VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
                       ON CONFLICT (ticket_id) DO NOTHING""",
                    t["ticket_id"], t["customer_email"], t["subject"],
                    t["body"], t.get("source", "email"),
                    created_at, t.get("tier", 1), t.get("expected_action"),
                )

            await conn.execute(
                """INSERT INTO knowledge_base (content)
                   SELECT $1
                   WHERE NOT EXISTS (SELECT 1 FROM knowledge_base)""",
                kb_content,
            )

    logger.info(
        "Seeded: %d customers, %d products, %d orders, %d tickets, knowledge_base",
        len(customers), len(products), len(orders), len(tickets),
    )


# ═══════════════════════════════════════════════════════════════
# Domain CRUD — Customers
# ═══════════════════════════════════════════════════════════════

async def db_get_customer_by_email(email: str) -> dict[str, Any] | None:
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM customers WHERE email = $1", email.lower().strip()
        )
        return _customer_row_to_dict(row) if row else None


async def db_get_customer_by_id(customer_id: str) -> dict[str, Any] | None:
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM customers WHERE customer_id = $1", customer_id
        )
        return _customer_row_to_dict(row) if row else None


def _customer_row_to_dict(row: asyncpg.Record) -> dict[str, Any]:
    d = dict(row)
    if isinstance(d.get("address"), str):
        d["address"] = json.loads(d["address"])
    return d


# ═══════════════════════════════════════════════════════════════
# Domain CRUD — Orders
# ═══════════════════════════════════════════════════════════════

async def db_get_order(order_id: str) -> dict[str, Any] | None:
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM orders WHERE order_id = $1", order_id
        )
        return dict(row) if row else None


async def db_get_orders_by_customer(customer_id: str) -> list[dict[str, Any]]:
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM orders WHERE customer_id = $1 ORDER BY order_date DESC",
            customer_id,
        )
        return [dict(r) for r in rows]


async def db_update_order(order_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    if not _pool or not updates:
        return None

    set_clauses = []
    values = []
    idx = 1

    allowed = {
        "status", "delivery_date", "return_deadline",
        "refund_status", "notes", "quantity", "amount",
    }

    for key, value in updates.items():
        if key not in allowed:
            continue
        idx += 1
        set_clauses.append(f"{key} = ${idx}")
        values.append(value)

    if not set_clauses:
        return None

    query = f"UPDATE orders SET {', '.join(set_clauses)} WHERE order_id = $1 RETURNING *"
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(query, order_id, *values)
        return dict(row) if row else None


# ═══════════════════════════════════════════════════════════════
# Domain CRUD — Products
# ═══════════════════════════════════════════════════════════════

async def db_get_product(product_id: str) -> dict[str, Any] | None:
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM products WHERE product_id = $1", product_id
        )
        return dict(row) if row else None


# ═══════════════════════════════════════════════════════════════
# Domain CRUD — Knowledge Base
# ═══════════════════════════════════════════════════════════════

async def db_get_knowledge_base() -> str | None:
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        content = await conn.fetchval(
            "SELECT content FROM knowledge_base ORDER BY id LIMIT 1"
        )
        return content


# ═══════════════════════════════════════════════════════════════
# Domain CRUD — Tickets
# ═══════════════════════════════════════════════════════════════

async def db_get_all_tickets() -> list[dict[str, Any]]:
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM tickets ORDER BY created_at")
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════
# Operational CRUD — Audit
# ═══════════════════════════════════════════════════════════════

async def db_create_audit(ticket_id: str) -> None:
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO ticket_audit (ticket_id, status, started_at)
               VALUES ($1, 'queued', $2)
               ON CONFLICT (ticket_id) DO NOTHING""",
            ticket_id, datetime.utcnow(),
        )


async def db_update_audit(ticket_id: str, **fields: Any) -> None:
    if not _pool or not fields:
        return

    set_clauses = []
    values = []
    idx = 1

    column_map = {
        "status": "status",
        "category": "category",
        "priority": "priority",
        "confidence": "confidence",
        "tool_calls": "tool_calls",
        "reasoning": "reasoning",
        "final_response": "final_response",
        "escalation_summary": "escalation_summary",
        "error": "error",
        "completed_at": "completed_at",
        "retries": "retries",
    }

    for key, value in fields.items():
        col = column_map.get(key)
        if col is None:
            continue
        idx += 1
        if col in ("tool_calls", "reasoning"):
            set_clauses.append(f"{col} = ${idx}::jsonb")
            values.append(json.dumps(value, default=str))
        elif col in ("status", "category", "priority"):
            set_clauses.append(f"{col} = ${idx}")
            values.append(value.value if hasattr(value, "value") else str(value))
        else:
            set_clauses.append(f"{col} = ${idx}")
            values.append(value)

    if not set_clauses:
        return

    query = f"UPDATE ticket_audit SET {', '.join(set_clauses)} WHERE ticket_id = $1"
    async with _pool.acquire() as conn:
        await conn.execute(query, ticket_id, *values)


async def db_get_audit(ticket_id: str) -> dict[str, Any] | None:
    if not _pool:
        return None
    async with _pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM ticket_audit WHERE ticket_id = $1", ticket_id
        )
        return dict(row) if row else None


async def db_get_all_audits() -> list[dict[str, Any]]:
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM ticket_audit ORDER BY started_at DESC"
        )
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════
# Operational CRUD — Cost Tracking
# ═══════════════════════════════════════════════════════════════

async def db_insert_cost(
    ticket_id: str,
    model_used: str,
    model_tier: str,
    input_tokens: int,
    output_tokens: int,
    estimated_cost: float,
    llm_calls: int,
    tool_calls: int,
) -> None:
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO cost_tracking
               (ticket_id, model_used, model_tier, input_tokens, output_tokens,
                estimated_cost, llm_calls, tool_calls)
               VALUES ($1, $2, $3, $4, $5, $6, $7, $8)""",
            ticket_id, model_used, model_tier,
            input_tokens, output_tokens, estimated_cost,
            llm_calls, tool_calls,
        )


async def db_get_all_costs() -> list[dict[str, Any]]:
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM cost_tracking ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]


# ═══════════════════════════════════════════════════════════════
# Operational CRUD — Dead Letter Queue
# ═══════════════════════════════════════════════════════════════

async def db_insert_dlq(ticket_id: str, error: str, retries: int) -> None:
    if not _pool:
        return
    async with _pool.acquire() as conn:
        await conn.execute(
            """INSERT INTO dead_letter_queue (ticket_id, error, retries)
               VALUES ($1, $2, $3)""",
            ticket_id, error, retries,
        )


async def db_get_all_dlq() -> list[dict[str, Any]]:
    if not _pool:
        return []
    async with _pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT * FROM dead_letter_queue ORDER BY created_at DESC"
        )
        return [dict(r) for r in rows]
