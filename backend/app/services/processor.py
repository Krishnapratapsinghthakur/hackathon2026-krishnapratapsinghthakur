"""Async ticket processor with concurrency, retry budgets, and dead-letter queue.

Key design decisions:
- asyncio.Semaphore for bounded concurrency (not sequential!)
- Exponential backoff retry with configurable budget
- Dead-letter queue for tickets that exhaust retries
- Every decision is audited
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.core.config import get_settings
from app.core.llm import get_active_model_name
from app.core.router import route_ticket
from app.db import store as loader
from app.graph.builder import get_graph
from app.models.schemas import (
    AuditEntry,
    BatchResponse,
    TicketCategory,
    TicketInput,
    TicketResult,
    TicketStatus,
    Priority,
)
from app.services import audit
from app.services.cost_tracker import track_ticket_cost
from app.core.exceptions import TicketValidationError
from app.services.validator import validate_ticket, release_ticket_id
from app.db import postgres as pg
from app.tools.transparency import tool_call_from_extracted

logger = logging.getLogger(__name__)

_dead_letter_queue: list[dict[str, Any]] = []
_dlq_lock = asyncio.Lock()


async def _add_to_dlq(ticket_id: str, error: str, retries: int) -> None:
    async with _dlq_lock:
        _dead_letter_queue.append({
            "ticket_id": ticket_id,
            "error": error,
            "retries_exhausted": retries,
            "timestamp": datetime.utcnow().isoformat(),
        })
    await pg.db_insert_dlq(ticket_id, error, retries)
    logger.warning("Dead-letter: ticket=%s error=%s retries=%d", ticket_id, error, retries)


async def get_dlq() -> list[dict[str, Any]]:
    db_rows = await pg.db_get_all_dlq()
    if db_rows:
        return [
            {
                "ticket_id": r["ticket_id"],
                "error": r["error"],
                "retries_exhausted": r["retries"],
                "timestamp": r["created_at"].isoformat() if r.get("created_at") else None,
            }
            for r in db_rows
        ]
    async with _dlq_lock:
        return list(_dead_letter_queue)


def _extract_tool_calls_from_messages(messages: list) -> list[dict[str, Any]]:
    """Extract structured tool call info from the message history."""
    tool_calls = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                tool_calls.append({
                    "tool_name": tc["name"],
                    "arguments": tc["args"],
                })
        elif isinstance(msg, ToolMessage):
            if tool_calls and tool_calls[-1].get("result") is None:
                try:
                    tool_calls[-1]["result"] = json.loads(msg.content)
                except (json.JSONDecodeError, TypeError):
                    tool_calls[-1]["result"] = msg.content
    return tool_calls


async def process_single_ticket(ticket: TicketInput) -> TicketResult:
    """Process one ticket through the LangGraph agent with retry logic."""
    settings = get_settings()
    graph = get_graph()

    # ── Pre-flight validation ──────────────────────────────────
    try:
        warnings = await validate_ticket(ticket)
    except TicketValidationError as e:
        logger.warning("Ticket rejected: %s", e)
        return TicketResult(
            ticket_id=ticket.ticket_id,
            status=TicketStatus.FAILED,
            response=f"Ticket rejected: {e.reason}",
            reasoning_steps=[f"Pre-flight validation failed: {e.reason}"],
        )

    audit_entry = await audit.create_entry(ticket.ticket_id)
    if warnings:
        for w in warnings:
            await audit.add_reasoning(ticket.ticket_id, f"[VALIDATION WARNING] {w}")
    await audit.update_entry(ticket.ticket_id, status=TicketStatus.PROCESSING)

    # ── Pre-fetch: verify customer + gather context ────────────
    customer = await loader.get_customer_by_email(ticket.customer_email)
    context_block = ""
    initial_reasoning: list[str] = []
    orders: list[dict[str, Any]] = []

    if customer is None:
        context_block = (
            f"\n⚠ CUSTOMER NOT FOUND: No customer registered with email "
            f"'{ticket.customer_email}'. You will need to ask for their "
            f"registered email or order ID to proceed.\n"
        )
        initial_reasoning.append(
            f"Pre-fetch: customer email '{ticket.customer_email}' not found in system."
        )
        await audit.add_reasoning(
            ticket.ticket_id,
            f"Customer not found for email '{ticket.customer_email}'",
        )
    else:
        orders = await loader.get_orders_by_customer(customer["customer_id"])
        orders_summary = ""
        if orders:
            order_lines = []
            for o in orders:
                order_lines.append(
                    f"  - {o['order_id']}: {o['status']} | ${o['amount']} | "
                    f"ordered {o['order_date']} | "
                    f"refund_status={o.get('refund_status') or 'none'}"
                )
            orders_summary = "\n".join(order_lines)
        else:
            orders_summary = "  (no orders found)"

        context_block = (
            f"\n── PRE-FETCHED CUSTOMER CONTEXT ──\n"
            f"Customer ID: {customer['customer_id']}\n"
            f"Name: {customer['name']}\n"
            f"Tier: {customer['tier'].upper()}\n"
            f"Member since: {customer['member_since']}\n"
            f"Total orders: {customer['total_orders']} | "
            f"Total spent: ${customer['total_spent']:.2f}\n"
            f"Internal notes: {customer['notes']}\n"
            f"\nRecent Orders:\n{orders_summary}\n"
            f"──────────────────────────────────\n"
        )
        initial_reasoning.append(
            f"Pre-fetch: verified customer {customer['name']} "
            f"(tier={customer['tier']}, {len(orders)} orders on file)."
        )
        await audit.add_reasoning(
            ticket.ticket_id,
            f"Customer verified: {customer['name']} ({customer['tier']}), "
            f"{len(orders)} orders found",
        )

    # ── Smart model routing ──────────────────────────────────
    customer_tier = customer["tier"] if customer else None
    order_amounts = [o["amount"] for o in orders] if customer and orders else []
    num_orders = len(orders) if customer and orders else 0

    model_tier, routing_reasons = route_ticket(
        ticket_body=ticket.body,
        ticket_subject=ticket.subject,
        customer_tier=customer_tier,
        order_amounts=order_amounts,
        num_orders=num_orders,
    )
    model_name = get_active_model_name(tier=model_tier)

    for reason in routing_reasons:
        initial_reasoning.append(f"[ROUTING] {reason}")
    await audit.add_reasoning(
        ticket.ticket_id,
        f"Model routed: tier={model_tier} model={model_name}",
    )

    ticket_prompt = (
        f"SUPPORT TICKET {ticket.ticket_id}\n"
        f"From: {ticket.customer_email}\n"
        f"Subject: {ticket.subject}\n"
        f"Source: {ticket.source}\n"
        f"Created: {ticket.created_at or 'N/A'}\n\n"
        f"Message:\n{ticket.body}\n"
        f"{context_block}\n"
        f"Use the pre-fetched context above. You still MUST call tools to verify details "
        f"and take actions (check eligibility, issue refunds, send replies, etc.). "
        f"Do NOT skip tool calls just because context is provided."
    )

    initial_state = {
        "messages": [HumanMessage(content=ticket_prompt)],
        "ticket_id": ticket.ticket_id,
        "customer_email": ticket.customer_email,
        "category": "unknown",
        "priority": "medium",
        "confidence": 0.0,
        "tool_call_log": [],
        "reasoning": initial_reasoning,
        "final_response": "",
        "escalation_summary": "",
        "status": "queued",
        "retry_count": 0,
        "model_tier": model_tier,
        "model_name": model_name,
    }

    last_error: str | None = None

    for attempt in range(settings.max_retries):
        try:
            result_state = await graph.ainvoke(initial_state)

            tool_calls = _extract_tool_calls_from_messages(result_state.get("messages", []))
            tool_call_models = [tool_call_from_extracted(tc) for tc in tool_calls]
            for tc in tool_calls:
                await audit.log_tool_call(
                    ticket.ticket_id,
                    tc["tool_name"],
                    tc.get("arguments", {}),
                    tc.get("result"),
                    tc.get("error"),
                )

            status_str = result_state.get("status", "resolved")
            try:
                status = TicketStatus(status_str)
            except ValueError:
                status = TicketStatus.RESOLVED

            cat_str = result_state.get("category", "unknown")
            try:
                category = TicketCategory(cat_str)
            except ValueError:
                category = TicketCategory.UNKNOWN

            pri_str = result_state.get("priority", "medium")
            try:
                priority = Priority(pri_str)
            except ValueError:
                priority = Priority.MEDIUM

            confidence = result_state.get("confidence", 0.7)
            reasoning = result_state.get("reasoning", [])

            await audit.update_entry(
                ticket.ticket_id,
                status=status,
                category=category,
                priority=priority,
                confidence=confidence,
                reasoning=reasoning,
                final_response=result_state.get("final_response", ""),
                escalation_summary=result_state.get("escalation_summary", ""),
                completed_at=datetime.utcnow(),
                retries=attempt,
            )

            # ── Cost tracking ──────────────────────────────────
            await track_ticket_cost(
                ticket_id=ticket.ticket_id,
                model_name=model_name,
                model_tier=model_tier,
                messages=result_state.get("messages", []),
            )

            return TicketResult(
                ticket_id=ticket.ticket_id,
                status=status,
                category=category,
                priority=priority,
                confidence=confidence,
                response=result_state.get("final_response", ""),
                escalation_summary=result_state.get("escalation_summary") or None,
                tool_calls_count=len(tool_call_models),
                tool_calls=tool_call_models,
                reasoning_steps=reasoning,
                model_used=model_name,
                model_tier=model_tier,
            )

        except Exception as e:
            last_error = str(e)
            logger.error(
                "Ticket %s attempt %d/%d failed: %s",
                ticket.ticket_id, attempt + 1, settings.max_retries, last_error,
            )
            await audit.add_reasoning(
                ticket.ticket_id,
                f"Attempt {attempt + 1} failed: {last_error}",
            )

            if attempt < settings.max_retries - 1:
                backoff = settings.retry_backoff_base ** attempt
                await asyncio.sleep(backoff)

    await _add_to_dlq(ticket.ticket_id, last_error or "Unknown error", settings.max_retries)
    await release_ticket_id(ticket.ticket_id)
    await audit.update_entry(
        ticket.ticket_id,
        status=TicketStatus.FAILED,
        error=last_error,
        completed_at=datetime.utcnow(),
        retries=settings.max_retries,
    )

    return TicketResult(
        ticket_id=ticket.ticket_id,
        status=TicketStatus.FAILED,
        response=f"Failed after {settings.max_retries} retries: {last_error}",
        reasoning_steps=[f"Exhausted {settings.max_retries} retries. Sent to dead-letter queue."],
        tool_calls=[],
        tool_calls_count=0,
    )


async def process_batch(tickets: list[TicketInput]) -> BatchResponse:
    """Process multiple tickets concurrently with bounded parallelism."""
    settings = get_settings()
    semaphore = asyncio.Semaphore(settings.max_concurrent_tickets)
    start = time.monotonic()

    async def _bounded(ticket: TicketInput) -> TicketResult:
        async with semaphore:
            return await process_single_ticket(ticket)

    results = await asyncio.gather(
        *[_bounded(t) for t in tickets],
        return_exceptions=False,
    )

    dlq = await get_dlq()
    elapsed = time.monotonic() - start

    logger.info(
        "Batch complete: %d tickets in %.2fs (%d failed)",
        len(tickets), elapsed, len([r for r in results if r.status == TicketStatus.FAILED]),
    )

    return BatchResponse(
        total=len(tickets),
        results=results,
        processing_time_seconds=round(elapsed, 3),
        dead_letter=dlq,
    )
