"""LangGraph state definition for the support resolution agent."""

from __future__ import annotations

import operator
from typing import Annotated, Any, Sequence

from langchain_core.messages import BaseMessage
from langgraph.graph import MessagesState
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """Full state tracked across the support resolution graph.

    messages: the LangChain message history (HumanMessage, AIMessage, ToolMessage)
    ticket_id: current ticket being processed
    customer_email: email from the ticket
    category: classified ticket category
    priority: classified priority
    confidence: agent's self-assessed confidence (0.0–1.0)
    tool_call_log: structured log of every tool invocation
    reasoning: step-by-step reasoning trace
    final_response: the customer-facing reply
    escalation_summary: if escalated, the summary
    status: queued | processing | resolved | escalated | failed
    retry_count: how many times this ticket has been retried
    messages: Annotated list for LangGraph's message reducer
    """

    messages: Annotated[Sequence[BaseMessage], operator.add]
    ticket_id: str
    customer_email: str
    category: str
    priority: str
    confidence: float
    tool_call_log: list[dict[str, Any]]
    reasoning: list[str]
    final_response: str
    escalation_summary: str
    status: str
    retry_count: int
    model_tier: str
    model_name: str
