from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings
from app.db.postgres import is_connected as db_connected
from app.core.cache import is_connected as cache_connected

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    settings = get_settings()

    celery_status = "configured" if settings.celery_broker_url else "disabled"

    return {
        "status": "ok",
        "environment": settings.environment,
        "database": "postgres" if db_connected() else "in-memory",
        "cache": "redis" if cache_connected() else "disabled",
        "worker": celery_status,
        "provider": settings.resolved_provider,
        "model_fast": settings.resolved_model_fast,
        "model_power": settings.resolved_model_power,
    }
