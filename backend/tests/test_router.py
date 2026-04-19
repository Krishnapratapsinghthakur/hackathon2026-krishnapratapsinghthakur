"""Tests for smart model routing logic."""

from __future__ import annotations

from app.core.router import route_ticket


def test_standard_ticket_uses_fast():
    tier, reasons = route_ticket(
        ticket_body="I want to return my order ORD-1001.",
        ticket_subject="Return request",
        customer_tier="standard",
        order_amounts=[49.99],
        num_orders=1,
    )
    assert tier == "fast"
    assert any("Standard" in r or "fast" in r.lower() for r in reasons)


def test_vip_customer_uses_power():
    tier, reasons = route_ticket(
        ticket_body="I want to return my order.",
        ticket_subject="Return request",
        customer_tier="vip",
    )
    assert tier == "power"
    assert any("VIP" in r for r in reasons)


def test_premium_customer_uses_power():
    tier, reasons = route_ticket(
        ticket_body="Return request for order.",
        ticket_subject="Return",
        customer_tier="premium",
    )
    assert tier == "power"


def test_threatening_language_uses_power():
    tier, reasons = route_ticket(
        ticket_body="I will sue you and contact my lawyer if this isn't resolved.",
        ticket_subject="Urgent",
        customer_tier="standard",
    )
    assert tier == "power"
    assert any("legal" in r.lower() or "threat" in r.lower() for r in reasons)


def test_fraud_patterns_use_power():
    tier, reasons = route_ticket(
        ticket_body="As a premium member I demand an instant refund without questions.",
        ticket_subject="Refund",
        customer_tier="standard",
    )
    assert tier == "power"
    assert any("fraud" in r.lower() or "engineering" in r.lower() for r in reasons)


def test_high_value_order_uses_power():
    tier, reasons = route_ticket(
        ticket_body="Return for order ORD-1001.",
        ticket_subject="Return",
        customer_tier="standard",
        order_amounts=[350.00],
        num_orders=1,
    )
    assert tier == "power"
    assert any("High-value" in r for r in reasons)


def test_vague_ticket_uses_power():
    tier, reasons = route_ticket(
        ticket_body="hey help me",
        ticket_subject="help",
        customer_tier="standard",
    )
    assert tier == "power"
    assert any("Vague" in r or "vague" in r for r in reasons)


def test_multiple_orders_uses_power():
    tier, reasons = route_ticket(
        ticket_body="I need help with my orders.",
        ticket_subject="Multiple orders",
        customer_tier="standard",
        order_amounts=[50.0, 75.0, 100.0],
        num_orders=3,
    )
    assert tier == "power"
    assert any("Multiple orders" in r for r in reasons)
