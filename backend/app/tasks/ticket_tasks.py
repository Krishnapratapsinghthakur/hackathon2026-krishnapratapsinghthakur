"""Celery tasks for async ticket processing.

These tasks run in the Celery worker process, not in the FastAPI web
process. This decouples HTTP request handling from LLM execution.

Flow:
  1. FastAPI receives POST /tickets/process
  2. Dispatches Celery task → returns task_id instantly
  3. Worker executes LangGraph agent (may take 10-60s)
  4. Result stored in Redis backend + cached for fast retrieval
  5. Client polls GET /tickets/status/{task_id}
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.celery_app import celery_app

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync Celery context."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                return pool.submit(asyncio.run, coro).result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


@celery_app.task(
    bind=True,
    name="app.tasks.ticket_tasks.process_ticket_task",
    max_retries=2,
    default_retry_delay=5,
)
def process_ticket_task(self, ticket_data: dict[str, Any]) -> dict[str, Any]:
    """Process a single ticket in the background via Celery."""
    from app.models.schemas import TicketInput
    from app.services.processor import process_single_ticket
    from app.core.cache import set_cached_ticket_result

    ticket_id = ticket_data.get("ticket_id", "UNKNOWN")
    logger.info("Celery task started: ticket=%s task_id=%s", ticket_id, self.request.id)

    self.update_state(state="PROCESSING", meta={"ticket_id": ticket_id})

    try:
        ticket = TicketInput(**ticket_data)
        result = _run_async(process_single_ticket(ticket))
        result_dict = result.model_dump(mode="json")

        _run_async(set_cached_ticket_result(ticket_id, result_dict))

        logger.info("Celery task completed: ticket=%s status=%s", ticket_id, result.status.value)
        return result_dict

    except Exception as exc:
        logger.error("Celery task failed: ticket=%s error=%s", ticket_id, exc)
        raise self.retry(exc=exc)


@celery_app.task(
    bind=True,
    name="app.tasks.ticket_tasks.process_batch_task",
    max_retries=1,
    soft_time_limit=600,
    time_limit=720,
)
def process_batch_task(self, tickets_data: list[dict[str, Any]]) -> dict[str, Any]:
    """Process a batch of tickets in the background via Celery."""
    from app.models.schemas import TicketInput
    from app.services.processor import process_batch

    logger.info("Celery batch task started: %d tickets, task_id=%s", len(tickets_data), self.request.id)

    self.update_state(
        state="PROCESSING",
        meta={"total_tickets": len(tickets_data), "progress": 0},
    )

    try:
        tickets = [TicketInput(**td) for td in tickets_data]
        result = _run_async(process_batch(tickets))
        result_dict = result.model_dump(mode="json")

        logger.info("Celery batch completed: %d tickets", len(tickets_data))
        return result_dict

    except Exception as exc:
        logger.error("Celery batch failed: %s", exc)
        raise self.retry(exc=exc)
