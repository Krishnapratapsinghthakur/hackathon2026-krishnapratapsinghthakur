"""Validate mock tool JSON outputs before they are returned to the LLM."""

from __future__ import annotations

import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.models.schemas import (
    CustomerInfo,
    EscalationResult,
    KnowledgeBaseResult,
    OrderInfo,
    ProductInfo,
    RefundEligibility,
    RefundResult,
    ReplyResult,
)

logger = logging.getLogger(__name__)


class ToolErrorEnvelope(BaseModel):
    """Tool responses that signal a domain error (not_found, invalid input, etc.)."""

    model_config = ConfigDict(extra="allow")
    error: str
    message: str = ""


_TOOL_MODELS: dict[str, type[BaseModel]] = {
    "get_customer": CustomerInfo,
    "get_order": OrderInfo,
    "get_product": ProductInfo,
    "search_knowledge_base": KnowledgeBaseResult,
    "check_refund_eligibility": RefundEligibility,
    "issue_refund": RefundResult,
    "send_reply": ReplyResult,
    "escalate": EscalationResult,
}


def _failure_payload(tool_name: str, detail: str) -> str:
    return json.dumps(
        {
            "error": "schema_validation_failed",
            "tool": tool_name,
            "message": detail[:800],
        }
    )


def validate_tool_output(tool_name: str, raw: str) -> str:
    """Parse and validate tool JSON. On failure return a controlled envelope (never pass through invalid JSON)."""
    model = _TOOL_MODELS.get(tool_name)
    if model is None:
        logger.warning("Unknown tool for validation: %s", tool_name)
        return _failure_payload(tool_name, "Unknown tool name")

    try:
        data: Any = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as e:
        logger.info("Tool %s returned non-JSON: %s", tool_name, e)
        return _failure_payload(tool_name, "Tool output was not valid JSON")

    if not isinstance(data, dict):
        return _failure_payload(tool_name, "Tool output JSON must be an object")

    if isinstance(data.get("error"), str):
        try:
            ToolErrorEnvelope.model_validate(data)
        except ValidationError as e:
            return _failure_payload(tool_name, f"Invalid error envelope: {e}")
        return json.dumps(data)

    try:
        model.model_validate(data)
    except ValidationError as e:
        logger.info("Tool %s output failed schema: %s", tool_name, e)
        return _failure_payload(tool_name, str(e))
    return json.dumps(data)
