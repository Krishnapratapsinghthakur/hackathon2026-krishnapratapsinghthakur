"""Audit log service — structured decision logging for every ticket.

Write-through pattern: in-memory for fast access + Postgres for persistence.
If DB is not connected, in-memory still works (graceful fallback).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from typing import Any

from app.db import postgres as pg
from app.models.schemas import AuditEntry, TicketStatus, ToolCall
from app.tools.transparency import tool_call_from_extracted

logger = logging.getLogger(__name__)

_audit_store: dict[str, AuditEntry] = {}
_lock = asyncio.Lock()


async def create_entry(ticket_id: str) -> AuditEntry:
    entry = AuditEntry(
        ticket_id=ticket_id,
        status=TicketStatus.QUEUED,
        started_at=datetime.utcnow(),
    )
    async with _lock:
        _audit_store[ticket_id] = entry
    await pg.db_create_audit(ticket_id)
    return entry


async def update_entry(ticket_id: str, **updates: Any) -> AuditEntry | None:
    async with _lock:
        entry = _audit_store.get(ticket_id)
        if entry is None:
            return None
        for key, value in updates.items():
            if hasattr(entry, key):
                setattr(entry, key, value)

    db_fields = {}
    for key, value in updates.items():
        if key in (
            "status", "category", "priority", "confidence",
            "final_response", "escalation_summary", "error",
            "completed_at", "retries",
        ):
            db_fields[key] = value
    if "tool_calls" in updates:
        db_fields["tool_calls"] = [tc.model_dump() for tc in updates["tool_calls"]]
    if "reasoning" in updates:
        db_fields["reasoning"] = updates["reasoning"]

    if db_fields:
        await pg.db_update_audit(ticket_id, **db_fields)

    return entry


async def log_tool_call(
    ticket_id: str,
    tool_name: str,
    arguments: dict[str, Any],
    result: Any = None,
    error: str | None = None,
) -> None:
    tc = tool_call_from_extracted(
        {
            "tool_name": tool_name,
            "arguments": arguments,
            "result": result,
            "error": error,
        }
    )
    tool_calls_list = []
    async with _lock:
        entry = _audit_store.get(ticket_id)
        if entry:
            entry.tool_calls.append(tc)
            tool_calls_list = [t.model_dump() for t in entry.tool_calls]

    if tool_calls_list:
        await pg.db_update_audit(ticket_id, tool_calls=tool_calls_list)

    logger.debug("Tool call logged: ticket=%s tool=%s", ticket_id, tool_name)


async def add_reasoning(ticket_id: str, step: str) -> None:
    reasoning_list = []
    async with _lock:
        entry = _audit_store.get(ticket_id)
        if entry:
            entry.reasoning.append(step)
            reasoning_list = list(entry.reasoning)

    if reasoning_list:
        await pg.db_update_audit(ticket_id, reasoning=reasoning_list)


async def get_entry(ticket_id: str) -> AuditEntry | None:
    async with _lock:
        entry = _audit_store.get(ticket_id)
        if entry:
            return entry

    row = await pg.db_get_audit(ticket_id)
    if row:
        return _row_to_audit_entry(row)
    return None


async def get_all_entries() -> list[AuditEntry]:
    async with _lock:
        if _audit_store:
            return list(_audit_store.values())

    rows = await pg.db_get_all_audits()
    return [_row_to_audit_entry(r) for r in rows]


def _row_to_audit_entry(row: dict[str, Any]) -> AuditEntry:
    tool_calls_raw = row.get("tool_calls") or []
    if isinstance(tool_calls_raw, str):
        tool_calls_raw = json.loads(tool_calls_raw)

    reasoning_raw = row.get("reasoning") or []
    if isinstance(reasoning_raw, str):
        reasoning_raw = json.loads(reasoning_raw)

    return AuditEntry(
        ticket_id=row["ticket_id"],
        status=row.get("status", "queued"),
        category=row.get("category"),
        priority=row.get("priority"),
        confidence=row.get("confidence"),
        tool_calls=[ToolCall(**tc) if isinstance(tc, dict) else tc for tc in tool_calls_raw],
        reasoning=reasoning_raw,
        final_response=row.get("final_response"),
        escalation_summary=row.get("escalation_summary"),
        error=row.get("error"),
        started_at=row.get("started_at", datetime.utcnow()),
        completed_at=row.get("completed_at"),
        retries=row.get("retries", 0),
    )
