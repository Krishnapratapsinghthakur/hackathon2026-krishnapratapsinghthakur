from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.models.schemas import AuditEntry
from app.services import audit as audit_service
from app.services.processor import get_dlq

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[AuditEntry])
async def get_audit_log():
    """Full audit trail of all processed tickets."""
    return await audit_service.get_all_entries()


@router.get("/dlq")
async def get_dead_letter_queue():
    """Tickets that failed after exhausting all retries."""
    return await get_dlq()


@router.get("/{ticket_id}", response_model=AuditEntry)
async def get_ticket_audit(ticket_id: str):
    """Detailed audit trail for a specific ticket."""
    entry = await audit_service.get_entry(ticket_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No audit entry for ticket '{ticket_id}'.")
    return entry
