"""ShopWave Autonomous Support Resolution Agent — Application entry point."""

from __future__ import annotations

import logging
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.routes import audit, health, tickets
from app.api.routes import settings as settings_routes
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.security import verify_api_key, request_id_var
from app.db.store import ensure_loaded
from app.db.postgres import init_db, close_db
from app.core.cache import init_cache, close_cache

setup_logging()
logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await ensure_loaded()
    db_ok = await init_db()
    cache_ok = await init_cache()
    logger.info(
        "ShopWave Support Agent ready (db=%s, cache=%s)",
        "postgres" if db_ok else "in-memory",
        "redis" if cache_ok else "disabled",
    )
    yield
    await close_cache()
    await close_db()
    logger.info("ShopWave Support Agent shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    auth_deps = []
    if settings.api_key:
        auth_deps.append(Depends(verify_api_key))

    application = FastAPI(
        title="ShopWave Autonomous Support Resolution Agent",
        description=(
            "AI-powered support agent that ingests, classifies, and autonomously "
            "resolves customer support tickets using LangGraph orchestration."
        ),
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        dependencies=auth_deps,
    )

    origins = [
        o.strip()
        for o in settings.cors_origins.split(",")
        if o.strip()
    ]

    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True if origins != ["*"] else False,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    application.state.limiter = limiter
    application.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    register_exception_handlers(application)

    @application.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_var.set(rid)
        response: Response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    application.include_router(health.router)
    application.include_router(tickets.router)
    application.include_router(audit.router)
    application.include_router(settings_routes.router)

    return application


app = create_app()
