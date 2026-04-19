#!/usr/bin/env python3
"""Delete operational rows (audits, costs, DLQ). Does not touch seed domain tables."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# repo root = backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings


async def main() -> None:
    import asyncpg

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not set — nothing to clear in Postgres.")
        sys.exit(0)

    conn = await asyncpg.connect(dsn=settings.database_url)
    try:
        async with conn.transaction():
            n_dlq = await conn.execute("DELETE FROM dead_letter_queue")
            n_cost = await conn.execute("DELETE FROM cost_tracking")
            n_audit = await conn.execute("DELETE FROM ticket_audit")
        # asyncpg returns "DELETE N"
        print(f"{n_dlq.strip()}; {n_cost.strip()}; {n_audit.strip()}")
        print("Domain tables (tickets, customers, orders, products) were not modified.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
