"""Celery application for background ticket processing.

Architecture:
  FastAPI (web) → Celery task → LangGraph agent → Postgres + Redis

The web process accepts tickets and returns a task_id immediately.
The Celery worker picks up the task, runs the LLM graph, and stores
the result in Redis (fast) + Postgres (durable).

The client polls /tickets/status/{task_id} until completion.
"""

from __future__ import annotations

import os

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "shopwave",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    result_expires=3600,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=120,
    task_time_limit=180,
    task_default_queue="tickets",
    task_routes={
        "app.tasks.ticket_tasks.process_ticket_task": {"queue": "tickets"},
        "app.tasks.ticket_tasks.process_batch_task": {"queue": "batch"},
    },
)

celery_app.autodiscover_tasks(["app.tasks"])
