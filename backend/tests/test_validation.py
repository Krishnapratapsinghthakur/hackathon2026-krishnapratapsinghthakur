"""Tests for input validation and schema enforcement."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models.schemas import TicketInput


def test_valid_ticket_accepted():
    ticket = TicketInput(
        ticket_id="TKT-001",
        customer_email="alice@email.com",
        subject="Help",
        body="I need help with my order.",
    )
    assert ticket.ticket_id == "TKT-001"
    assert ticket.customer_email == "alice@email.com"


def test_email_normalized_to_lowercase():
    ticket = TicketInput(
        ticket_id="TKT-002",
        customer_email="ALICE@Email.COM",
        subject="Help",
        body="Need help.",
    )
    assert ticket.customer_email == "alice@email.com"


def test_invalid_email_rejected():
    with pytest.raises(ValidationError) as exc_info:
        TicketInput(
            ticket_id="TKT-003",
            customer_email="not-an-email",
            subject="Help",
            body="Need help.",
        )
    assert "email" in str(exc_info.value).lower()


def test_empty_ticket_id_rejected():
    with pytest.raises(ValidationError):
        TicketInput(
            ticket_id="",
            customer_email="alice@email.com",
            subject="Help",
            body="Need help.",
        )


def test_blank_body_rejected():
    with pytest.raises(ValidationError):
        TicketInput(
            ticket_id="TKT-004",
            customer_email="alice@email.com",
            subject="Help",
            body="   ",
        )


def test_whitespace_ticket_id_stripped():
    ticket = TicketInput(
        ticket_id="  TKT-005  ",
        customer_email="alice@email.com",
        subject="Help",
        body="Need help.",
    )
    assert ticket.ticket_id == "TKT-005"


def test_default_source_is_email():
    ticket = TicketInput(
        ticket_id="TKT-006",
        customer_email="alice@email.com",
        subject="Help",
        body="Need help.",
    )
    assert ticket.source == "email"


def test_default_tier_is_one():
    ticket = TicketInput(
        ticket_id="TKT-007",
        customer_email="alice@email.com",
        subject="Help",
        body="Need help.",
    )
    assert ticket.tier == 1


@pytest.mark.asyncio
async def test_invalid_ticket_returns_422(client, invalid_ticket):
    resp = await client.post("/tickets/process", json=invalid_ticket)
    assert resp.status_code == 422
