from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings, PRESETS
from app.core.llm import MODEL_COSTS
from app.services.cost_tracker import get_cost_summary

router = APIRouter(prefix="/settings", tags=["settings & cost"])


@router.get("")
async def get_current_settings():
    """View current LLM configuration — shows resolved provider/models based on environment."""
    settings = get_settings()
    return {
        "environment": settings.environment,
        "resolved_provider": settings.resolved_provider,
        "resolved_models": {
            "fast": settings.resolved_model_fast,
            "power": settings.resolved_model_power,
        },
        "smart_routing": settings.llm_smart_routing,
        "temperature": settings.llm_temperature,
        "cost_tracking": settings.cost_tracking_enabled,
        "budget_per_batch": settings.cost_budget_per_batch,
        "confidence_threshold": settings.confidence_threshold,
        "max_concurrent": settings.max_concurrent_tickets,
        "max_retries": settings.max_retries,
        "llm_rate_limit": {
            "max_requests_per_minute": settings.llm_max_requests_per_minute,
            "max_concurrent_calls": settings.llm_max_concurrent_calls,
            "min_interval_seconds": settings.llm_min_interval_seconds,
            "429_max_retries": settings.llm_429_max_retries,
            "429_retry_base_seconds": settings.llm_429_retry_base_seconds,
            "429_retry_max_seconds": settings.llm_429_retry_max_seconds,
        },
        "presets": PRESETS,
        "how_to_switch": "Set ENVIRONMENT=production in .env to switch to paid models.",
    }


@router.get("/models")
async def list_supported_models():
    """List all supported models with their pricing."""
    settings = get_settings()
    return {
        "current_environment": settings.environment,
        "active": {
            "provider": settings.resolved_provider,
            "fast": settings.resolved_model_fast,
            "power": settings.resolved_model_power,
        },
        "presets": PRESETS,
        "pricing_per_1m_tokens": MODEL_COSTS,
    }


@router.get("/costs")
async def get_costs():
    """Token usage and cost breakdown for all processed tickets."""
    return await get_cost_summary()
