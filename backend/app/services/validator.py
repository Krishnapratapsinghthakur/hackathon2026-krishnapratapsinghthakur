"""Pre-flight ticket validation before sending to the LLM graph."""

from __future__ import annotations

import asyncio
import logging

from app.core.exceptions import TicketValidationError
from app.models.schemas import TicketInput

logger = logging.getLogger(__name__)

_processed_ids: set[str] = set()
_id_lock = asyncio.Lock()


async def validate_ticket(ticket: TicketInput) -> list[str]:
    """Run pre-flight checks. Returns list of warnings (empty = all good).
    Raises TicketValidationError for hard failures.
    """
    warnings: list[str] = []

    async with _id_lock:
        if ticket.ticket_id in _processed_ids:
            raise TicketValidationError(
                ticket.ticket_id,
                f"Duplicate ticket_id '{ticket.ticket_id}' — already processed or in progress.",
            )
        _processed_ids.add(ticket.ticket_id)

    body_stripped = ticket.body.strip()
    word_count = len(body_stripped.split())
    if word_count < 3:
        warnings.append(
            f"Ticket body is very short ({word_count} words). "
            "Agent may need to ask clarifying questions."
        )

    if ticket.source not in {"email", "ticket_queue", "chat", "phone", "api"}:
        warnings.append(f"Unrecognized source '{ticket.source}'. Processing anyway.")

    logger.info(
        "Ticket %s validated: %d warning(s)",
        ticket.ticket_id, len(warnings),
    )
    return warnings


async def release_ticket_id(ticket_id: str) -> None:
    async with _id_lock:
        _processed_ids.discard(ticket_id)
