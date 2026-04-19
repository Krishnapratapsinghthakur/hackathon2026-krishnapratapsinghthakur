"""Security middleware: API key authentication and request ID correlation."""

from __future__ import annotations

import uuid
import logging
from contextvars import ContextVar

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from app.core.config import get_settings

logger = logging.getLogger(__name__)

request_id_var: ContextVar[str] = ContextVar("request_id", default="")

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

PUBLIC_PATHS = {"/health", "/docs", "/redoc", "/openapi.json"}


async def verify_api_key(
    api_key: str | None = Security(_api_key_header),
) -> str | None:
    """Validate API key if configured. Skip if API_KEY is not set (dev mode)."""
    settings = get_settings()

    if not settings.api_key:
        return None

    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API key. Provide X-API-Key header.",
        )

    if api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API key.",
        )

    return api_key
