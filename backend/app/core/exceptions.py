"""Application-level exceptions and FastAPI exception handlers."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class TicketValidationError(Exception):
    def __init__(self, ticket_id: str, reason: str):
        self.ticket_id = ticket_id
        self.reason = reason
        super().__init__(f"Ticket {ticket_id} rejected: {reason}")


class TicketNotFoundError(Exception):
    def __init__(self, ticket_id: str):
        self.ticket_id = ticket_id
        super().__init__(f"Ticket '{ticket_id}' not found")


class ProcessingError(Exception):
    pass


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(TicketValidationError)
    async def validation_handler(request: Request, exc: TicketValidationError):
        logger.warning("Validation error: %s", exc)
        return JSONResponse(
            status_code=422,
            content={
                "error": "validation_error",
                "ticket_id": exc.ticket_id,
                "detail": exc.reason,
            },
        )

    @app.exception_handler(TicketNotFoundError)
    async def not_found_handler(request: Request, exc: TicketNotFoundError):
        return JSONResponse(
            status_code=404,
            content={
                "error": "not_found",
                "detail": str(exc),
            },
        )

    @app.exception_handler(Exception)
    async def catch_all_handler(request: Request, exc: Exception):
        logger.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "detail": "An unexpected error occurred. Check server logs.",
            },
        )
