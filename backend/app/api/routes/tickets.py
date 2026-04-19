"""Ticket processing endpoints — sync and async (Celery) modes.

Two processing modes:
  - Sync:  POST /tickets/process         → blocks until result
  - Async: POST /tickets/process?async=1  → returns task_id instantly
  - Poll:  GET  /tickets/status/{task_id} → check task progress

Batch always uses Celery when available.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address

import uuid
from datetime import datetime

from app.core.cache import get_cached_ticket_result
from app.db.store import get_all_tickets
from app.models.schemas import BatchRequest, BatchResponse, QuickTicketInput, TicketInput, TicketResult
from app.services.processor import process_batch, process_single_ticket

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("/process", response_model=None)
@limiter.limit("30/minute")
async def process_ticket(
    request: Request,
    ticket: TicketInput,
    background: bool = Query(False, alias="async", description="Run in Celery background worker"),
):
    """Process a single ticket. Use ?async=true to dispatch to Celery and get a task_id."""
    if background:
        try:
            from app.tasks.ticket_tasks import process_ticket_task
            task = process_ticket_task.delay(ticket.model_dump(mode="json"))
            logger.info("Ticket %s dispatched to Celery: task_id=%s", ticket.ticket_id, task.id)
            return {
                "mode": "async",
                "task_id": task.id,
                "ticket_id": ticket.ticket_id,
                "status": "QUEUED",
                "poll_url": f"/tickets/status/{task.id}",
            }
        except Exception as e:
            logger.warning("Celery dispatch failed, falling back to sync: %s", e)

    logger.info("Processing ticket %s (sync)", ticket.ticket_id)
    result = await process_single_ticket(ticket)

    from app.core.cache import set_cached_ticket_result
    await set_cached_ticket_result(ticket.ticket_id, result.model_dump(mode="json"))

    return result


@router.post("/batch", response_model=None)
@limiter.limit("5/minute")
async def process_ticket_batch(
    request: Request,
    batch: BatchRequest,
    background: bool = Query(False, alias="async", description="Run in Celery background worker"),
):
    """Process multiple tickets. Use ?async=true for background processing."""
    tickets = list(batch.tickets)

    if batch.load_sample:
        raw = await get_all_tickets()
        for t in raw:
            tickets.append(TicketInput(**t))

    if not tickets:
        raise HTTPException(
            status_code=400,
            detail="No tickets provided and load_sample is false.",
        )

    if background:
        try:
            from app.tasks.ticket_tasks import process_batch_task
            tickets_data = [t.model_dump(mode="json") for t in tickets]
            task = process_batch_task.delay(tickets_data)
            logger.info("Batch of %d dispatched to Celery: task_id=%s", len(tickets), task.id)
            return {
                "mode": "async",
                "task_id": task.id,
                "total_tickets": len(tickets),
                "status": "QUEUED",
                "poll_url": f"/tickets/status/{task.id}",
            }
        except Exception as e:
            logger.warning("Celery dispatch failed, falling back to sync: %s", e)

    logger.info("Batch request: %d tickets (sync, sample=%s)", len(tickets), batch.load_sample)
    return await process_batch(tickets)


@router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """Poll the status of a Celery task. Returns result when complete."""
    try:
        from app.core.celery_app import celery_app
        result = celery_app.AsyncResult(task_id)
        status = result.status
    except Exception as e:
        raise HTTPException(
            status_code=503,
            detail=f"Celery backend not available: {type(e).__name__}",
        )

    response = {
        "task_id": task_id,
        "status": status,
    }

    if status == "PENDING":
        response["detail"] = "Task is waiting in queue."
    elif status == "PROCESSING":
        response["detail"] = "Task is being processed by worker."
        try:
            if result.info and isinstance(result.info, dict):
                response["meta"] = result.info
        except Exception:
            pass
    elif status == "SUCCESS":
        response["result"] = result.result
    elif status == "FAILURE":
        response["error"] = str(result.result)
    elif status == "RETRY":
        response["detail"] = "Task is being retried."

    return response


@router.post("/quick", response_model=None)
@limiter.limit("30/minute")
async def process_quick_ticket(
    request: Request,
    quick: QuickTicketInput,
    background: bool = Query(False, alias="async"),
):
    """Minimal ticket input — just email + message. System auto-generates ticket_id and subject.

    Designed for the UI: user types email and message, clicks send. That's it.
    """
    ticket_id = f"TKT-{uuid.uuid4().hex[:8].upper()}"

    words = quick.message.strip().split()
    subject = " ".join(words[:8])
    if len(words) > 8:
        subject += "..."

    ticket = TicketInput(
        ticket_id=ticket_id,
        customer_email=quick.customer_email,
        subject=subject,
        body=quick.message,
        source=quick.source,
        created_at=datetime.utcnow(),
        tier=1,
    )

    if background:
        try:
            from app.tasks.ticket_tasks import process_ticket_task
            task = process_ticket_task.delay(ticket.model_dump(mode="json"))
            return {
                "mode": "async",
                "task_id": task.id,
                "ticket_id": ticket_id,
                "status": "QUEUED",
                "poll_url": f"/tickets/status/{task.id}",
            }
        except Exception as e:
            logger.warning("Celery dispatch failed, falling back to sync: %s", e)

    result = await process_single_ticket(ticket)

    from app.core.cache import set_cached_ticket_result
    await set_cached_ticket_result(ticket_id, result.model_dump(mode="json"))

    return result


@router.get("/result/{ticket_id}")
async def get_cached_result(ticket_id: str):
    """Get the cached result of a previously processed ticket (Redis)."""
    cached = await get_cached_ticket_result(ticket_id)
    if cached is not None:
        return {"source": "cache", "result": cached}

    raise HTTPException(
        status_code=404,
        detail=f"No cached result for ticket '{ticket_id}'. Process the ticket first.",
    )


@router.get("/sample")
async def list_sample_tickets():
    """List all sample tickets available for processing."""
    return await get_all_tickets()
