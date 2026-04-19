"""Confidence calibration from tool trace (rubric: no overconfident answers without evidence)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

_READ_TOOLS = frozenset(
    {"get_customer", "get_order", "get_product", "search_knowledge_base", "check_refund_eligibility"}
)


def _tool_call_order(messages: list) -> list[str]:
    names: list[str] = []
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                n = tc.get("name")
                if n:
                    names.append(n)
    return names


def issue_refund_before_eligibility_check(messages: list) -> bool:
    """True if any issue_refund appears before the first check_refund_eligibility."""
    order = _tool_call_order(messages)
    first_check: int | None = None
    first_issue: int | None = None
    for i, name in enumerate(order):
        if name == "check_refund_eligibility" and first_check is None:
            first_check = i
        if name == "issue_refund" and first_issue is None:
            first_issue = i
    if first_issue is None:
        return False
    if first_check is None:
        return True
    return first_issue < first_check


def count_evidence_tool_hits(messages: list) -> int:
    """Count read/policy tool calls whose JSON body has no domain-level `error` key."""
    pending: dict[str, str] = {}
    hits = 0
    for msg in messages:
        if isinstance(msg, AIMessage) and msg.tool_calls:
            for tc in msg.tool_calls:
                tid = tc.get("id") or ""
                name = tc.get("name") or ""
                if tid:
                    pending[tid] = name
        elif isinstance(msg, ToolMessage):
            tid = getattr(msg, "tool_call_id", None) or ""
            name = pending.pop(tid, "")
            if name not in _READ_TOOLS:
                continue
            try:
                body = json.loads(msg.content)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(body, dict):
                continue
            if body.get("error") == "schema_validation_failed":
                continue
            if isinstance(body.get("error"), str):
                continue
            hits += 1
    return hits


def calibrate_confidence(
    messages: list,
    raw_confidence: float,
    *,
    needs_escalation: bool,
) -> tuple[float, list[str]]:
    """Return (calibrated_confidence, extra_reasoning_lines)."""
    notes: list[str] = []
    c = max(0.0, min(1.0, float(raw_confidence)))

    if issue_refund_before_eligibility_check(messages):
        c = min(c, 0.55)
        notes.append(
            "Calibration: issue_refund appeared before check_refund_eligibility — "
            "capping confidence (policy order violation)."
        )

    evidence = count_evidence_tool_hits(messages)
    if c >= 0.85 and evidence < 2:
        capped = min(c, 0.72)
        if capped < c:
            notes.append(
                f"Calibration: high confidence ({raw_confidence:.2f}) with only {evidence} "
                "verified read(s); capped to reflect limited evidence."
            )
        c = capped

    if needs_escalation:
        c = min(c, 0.65)
        notes.append("Calibration: model requested escalation — dampening confidence.")

    return c, notes
