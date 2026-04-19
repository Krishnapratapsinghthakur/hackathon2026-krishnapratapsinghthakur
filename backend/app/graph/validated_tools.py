"""Tool execution with JSON/schema validation before results reach the LLM."""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.messages import AIMessage, ToolMessage

from app.tools.mock_tools import ALL_TOOLS
from app.tools.output_validation import validate_tool_output

logger = logging.getLogger(__name__)

_TOOLS_BY_NAME = {t.name: t for t in ALL_TOOLS}


async def validated_tool_node(state: dict[str, Any]) -> dict[str, Any]:
    """Run tool calls from the last AIMessage and append validated ToolMessages."""
    messages = state.get("messages", [])
    if not messages:
        return {}

    last = messages[-1]
    if not isinstance(last, AIMessage) or not last.tool_calls:
        return {}

    out: list[ToolMessage] = []
    for tc in last.tool_calls:
        name = tc.get("name") or ""
        args = tc.get("args") or {}
        tid = tc.get("id") or ""
        tool = _TOOLS_BY_NAME.get(name)
        if tool is None:
            payload = json.dumps(
                {"error": "unknown_tool", "message": f"No tool registered as '{name}'."}
            )
            out.append(ToolMessage(content=payload, tool_call_id=tid))
            continue
        try:
            raw = await tool.ainvoke(args)
        except Exception as e:
            logger.warning("Tool %s invocation failed: %s", name, e)
            payload = json.dumps(
                {"error": "tool_invocation_failed", "message": str(e)[:500]}
            )
            out.append(ToolMessage(content=payload, tool_call_id=tid))
            continue
        if not isinstance(raw, str):
            raw = json.dumps(raw, default=str)
        validated = validate_tool_output(name, raw)
        out.append(ToolMessage(content=validated, tool_call_id=tid))

    return {"messages": out}
