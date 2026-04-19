"""Tests for tool output validation, calibration, and strict final JSON parsing."""

from __future__ import annotations

import json

from langchain_core.messages import AIMessage, ToolMessage

from app.graph.calibration import (
    calibrate_confidence,
    count_evidence_tool_hits,
    issue_refund_before_eligibility_check,
)
from app.graph.nodes import parse_result_node
from app.tools.output_validation import validate_tool_output


def test_validate_tool_accepts_customer_not_found_envelope():
    raw = json.dumps(
        {
            "error": "customer_not_found",
            "message": "No one here.",
        }
    )
    out = validate_tool_output("get_customer", raw)
    assert "customer_not_found" in out


def test_validate_tool_rejects_malformed_customer_success_shape():
    raw = json.dumps({"customer_id": "X"})
    out = validate_tool_output("get_customer", raw)
    data = json.loads(out)
    assert data.get("error") == "schema_validation_failed"
    assert data.get("tool") == "get_customer"


def test_validate_tool_accepts_full_customer():
    raw = json.dumps(
        {
            "customer_id": "C001",
            "name": "Alice",
            "email": "alice@example.com",
            "phone": "+1",
            "tier": "vip",
            "member_since": "2020-01-01",
            "total_orders": 1,
            "total_spent": 10.0,
            "address": {"street": "1", "city": "SF", "state": "CA", "zip": "94102"},
            "notes": "n",
        }
    )
    out = validate_tool_output("get_customer", raw)
    assert json.loads(out)["email"] == "alice@example.com"


def test_issue_refund_before_check_detected():
    m1 = AIMessage(
        content="",
        tool_calls=[
            {"name": "issue_refund", "args": {"order_id": "ORD-1", "amount": 1.0}, "id": "a"},
        ],
    )
    m2 = ToolMessage(content="{}", tool_call_id="a")
    m3 = AIMessage(
        content="",
        tool_calls=[
            {"name": "check_refund_eligibility", "args": {"order_id": "ORD-1"}, "id": "b"},
        ],
    )
    assert issue_refund_before_eligibility_check([m1, m2, m3]) is True


def test_count_evidence_skips_domain_errors():
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_customer", "args": {"email": "x"}, "id": "t1"},
        ],
    )
    tm = ToolMessage(
        content=json.dumps({"error": "customer_not_found", "message": "nope"}),
        tool_call_id="t1",
    )
    assert count_evidence_tool_hits([ai, tm]) == 0


def test_calibrate_caps_high_confidence_with_little_evidence():
    ai = AIMessage(
        content="",
        tool_calls=[
            {"name": "get_customer", "args": {"email": "x"}, "id": "t1"},
        ],
    )
    tm = ToolMessage(
        content=json.dumps(
            {
                "customer_id": "C001",
                "name": "Alice",
                "email": "alice@example.com",
                "phone": "+1",
                "tier": "vip",
                "member_since": "2020-01-01",
                "total_orders": 1,
                "total_spent": 10.0,
                "address": {"street": "1", "city": "SF", "state": "CA", "zip": "94102"},
                "notes": "n",
            }
        ),
        tool_call_id="t1",
    )
    messages = [ai, tm]
    c, notes = calibrate_confidence(messages, 0.95, needs_escalation=False)
    assert c <= 0.72
    assert any("Calibration" in n for n in notes)


def test_parse_result_needs_escalation_flag():
    payload = {
        "category": "warranty",
        "priority": "high",
        "confidence": 0.95,
        "reasoning": ["Customer needs human review."],
        "action_taken": "Escalated pending warranty desk.",
        "needs_escalation": True,
    }
    final = AIMessage(content=json.dumps(payload))
    state = {
        "messages": [final],
        "ticket_id": "TKT-X",
        "category": "unknown",
        "priority": "medium",
        "confidence": 0.7,
        "reasoning": [],
    }
    out = parse_result_node(state)
    assert out["status"] == "escalated"
    assert "Model flagged" in (out.get("escalation_summary") or "")


def test_parse_result_invalid_schema_lowers_confidence():
    final = AIMessage(
        content=json.dumps(
            {
                "category": "refund",
                "priority": "low",
                "confidence": 0.9,
                "reasoning": [],
                "action_taken": "x",
            }
        )
    )
    state = {
        "messages": [final],
        "ticket_id": "TKT-Y",
        "category": "unknown",
        "priority": "medium",
        "confidence": 0.9,
        "reasoning": [],
    }
    out = parse_result_node(state)
    assert out["confidence"] <= 0.45
    assert any("strict schema" in r.lower() for r in out["reasoning"])
