"""Token usage and cost tracking per ticket and per batch.

Counts tokens from LangChain message history and estimates cost
based on the model's pricing. Exposes running totals via API.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from app.core.llm import get_model_cost
from app.db import postgres as pg

logger = logging.getLogger(__name__)


@dataclass
class TicketCost:
    ticket_id: str
    model_used: str
    model_tier: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    llm_calls: int = 0
    tool_calls: int = 0
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticket_id": self.ticket_id,
            "model_used": self.model_used,
            "model_tier": self.model_tier,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.input_tokens + self.output_tokens,
            "estimated_cost_usd": round(self.estimated_cost_usd, 6),
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "timestamp": self.timestamp.isoformat(),
        }


_cost_log: list[TicketCost] = []
_lock = asyncio.Lock()


def _estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token for English text."""
    return max(1, len(text) // 4)


def count_tokens_from_messages(messages: list[BaseMessage]) -> tuple[int, int, int, int]:
    """Count approximate input/output tokens and LLM/tool calls from message history.

    Returns (input_tokens, output_tokens, llm_calls, tool_calls).
    """
    input_tokens = 0
    output_tokens = 0
    llm_calls = 0
    tool_calls = 0

    for msg in messages:
        tokens = _estimate_tokens(msg.content if isinstance(msg.content, str) else str(msg.content))

        if isinstance(msg, (SystemMessage, HumanMessage)):
            input_tokens += tokens
        elif isinstance(msg, ToolMessage):
            input_tokens += tokens
            tool_calls += 1
        elif isinstance(msg, AIMessage):
            if msg.tool_calls:
                output_tokens += tokens
                for tc in msg.tool_calls:
                    output_tokens += _estimate_tokens(str(tc.get("args", {})))
                    tool_calls += len(msg.tool_calls)
            else:
                output_tokens += tokens
            llm_calls += 1

    return input_tokens, output_tokens, llm_calls, tool_calls


def calculate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate estimated cost in USD based on token counts and model pricing."""
    pricing = get_model_cost(model_name)
    cost = (
        (input_tokens / 1_000_000) * pricing["input"]
        + (output_tokens / 1_000_000) * pricing["output"]
    )
    return cost


async def track_ticket_cost(
    ticket_id: str,
    model_name: str,
    model_tier: str,
    messages: list[BaseMessage],
) -> TicketCost:
    """Track and store cost for a processed ticket."""
    input_tokens, output_tokens, llm_calls, tool_calls = count_tokens_from_messages(messages)
    cost = calculate_cost(model_name, input_tokens, output_tokens)

    entry = TicketCost(
        ticket_id=ticket_id,
        model_used=model_name,
        model_tier=model_tier,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost_usd=cost,
        llm_calls=llm_calls,
        tool_calls=tool_calls,
    )

    async with _lock:
        _cost_log.append(entry)

    await pg.db_insert_cost(
        ticket_id=ticket_id,
        model_used=model_name,
        model_tier=model_tier,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        estimated_cost=cost,
        llm_calls=llm_calls,
        tool_calls=tool_calls,
    )

    logger.info(
        "Cost tracked: ticket=%s model=%s tier=%s tokens=%d+%d cost=$%.6f",
        ticket_id, model_name, model_tier,
        input_tokens, output_tokens, cost,
    )
    return entry


async def get_cost_summary() -> dict[str, Any]:
    """Get aggregate cost summary across all processed tickets."""
    async with _lock:
        entries = list(_cost_log)

    if not entries:
        return {
            "total_tickets": 0,
            "total_cost_usd": 0.0,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
            "total_tokens": 0,
            "by_model": {},
            "by_tier": {},
            "per_ticket": [],
        }

    total_cost = sum(e.estimated_cost_usd for e in entries)
    total_input = sum(e.input_tokens for e in entries)
    total_output = sum(e.output_tokens for e in entries)

    by_model: dict[str, dict[str, Any]] = {}
    by_tier: dict[str, dict[str, Any]] = {}

    for e in entries:
        if e.model_used not in by_model:
            by_model[e.model_used] = {"tickets": 0, "cost_usd": 0.0, "tokens": 0}
        by_model[e.model_used]["tickets"] += 1
        by_model[e.model_used]["cost_usd"] = round(
            by_model[e.model_used]["cost_usd"] + e.estimated_cost_usd, 6
        )
        by_model[e.model_used]["tokens"] += e.input_tokens + e.output_tokens

        if e.model_tier not in by_tier:
            by_tier[e.model_tier] = {"tickets": 0, "cost_usd": 0.0, "tokens": 0}
        by_tier[e.model_tier]["tickets"] += 1
        by_tier[e.model_tier]["cost_usd"] = round(
            by_tier[e.model_tier]["cost_usd"] + e.estimated_cost_usd, 6
        )
        by_tier[e.model_tier]["tokens"] += e.input_tokens + e.output_tokens

    return {
        "total_tickets": len(entries),
        "total_cost_usd": round(total_cost, 6),
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_tokens": total_input + total_output,
        "avg_cost_per_ticket": round(total_cost / len(entries), 6) if entries else 0.0,
        "by_model": by_model,
        "by_tier": by_tier,
        "per_ticket": [e.to_dict() for e in entries],
    }
