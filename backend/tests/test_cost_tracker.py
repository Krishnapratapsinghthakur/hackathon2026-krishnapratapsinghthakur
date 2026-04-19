"""Tests for cost tracking and token estimation."""

from __future__ import annotations

from app.core.llm import get_model_cost
from app.services.cost_tracker import (
    _estimate_tokens,
    calculate_cost,
    count_tokens_from_messages,
)

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


def test_estimate_tokens_basic():
    assert _estimate_tokens("hello world") >= 1
    assert _estimate_tokens("a" * 400) == 100


def test_estimate_tokens_empty():
    assert _estimate_tokens("") == 1


def test_groq_model_is_free():
    cost = get_model_cost("llama-3.3-70b-versatile")
    assert cost["input"] == 0.0
    assert cost["output"] == 0.0


def test_openai_model_has_cost():
    cost = get_model_cost("gpt-4o-mini")
    assert cost["input"] > 0
    assert cost["output"] > 0


def test_unknown_model_returns_default():
    cost = get_model_cost("some-unknown-model")
    assert "input" in cost
    assert "output" in cost


def test_calculate_cost_free_model():
    cost = calculate_cost("llama-3.3-70b-versatile", 10000, 5000)
    assert cost == 0.0


def test_calculate_cost_paid_model():
    cost = calculate_cost("gpt-4o-mini", 1_000_000, 1_000_000)
    assert cost > 0


def test_count_tokens_from_messages():
    messages = [
        SystemMessage(content="You are a support agent."),
        HumanMessage(content="I want a refund for ORD-1001."),
        AIMessage(content="Let me check that for you."),
    ]
    input_t, output_t, llm_calls, tool_calls = count_tokens_from_messages(messages)
    assert input_t > 0
    assert output_t > 0
    assert llm_calls == 1
    assert tool_calls == 0


def test_count_tokens_with_tool_calls():
    messages = [
        HumanMessage(content="Check my order."),
        AIMessage(
            content="",
            tool_calls=[{"name": "get_order", "args": {"order_id": "ORD-1001"}, "id": "1"}],
        ),
        ToolMessage(content='{"order_id": "ORD-1001", "status": "delivered"}', tool_call_id="1"),
        AIMessage(content="Your order has been delivered."),
    ]
    input_t, output_t, llm_calls, tool_calls = count_tokens_from_messages(messages)
    assert tool_calls > 0
    assert llm_calls == 2
