"""Build the LangGraph state machine for the support resolution agent.

Graph topology:
  classify -> agent -> (tools | parse_result)
                ^         |
                |_________|
  
  The agent loops: call LLM -> if tool_calls, execute them and loop back.
  When LLM returns no tool_calls, route to parse_result -> END.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from langchain_core.messages import AIMessage
from langgraph.graph import END, StateGraph

from app.graph.nodes import agent_node, classifier_node, parse_result_node
from app.graph.state import AgentState
from app.graph.validated_tools import validated_tool_node

logger = logging.getLogger(__name__)


def _should_continue(state: dict[str, Any]) -> Literal["tools", "parse_result"]:
    """Route after the agent node: if the last message has tool_calls, go to tools. Otherwise parse the result."""
    messages = state.get("messages", [])
    if not messages:
        return "parse_result"

    last = messages[-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "tools"
    return "parse_result"


def build_graph() -> StateGraph:
    """Construct and compile the support agent graph."""

    graph = StateGraph(AgentState)

    graph.add_node("classify", classifier_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", validated_tool_node)
    graph.add_node("parse_result", parse_result_node)

    graph.set_entry_point("classify")
    graph.add_edge("classify", "agent")

    graph.add_conditional_edges(
        "agent",
        _should_continue,
        {
            "tools": "tools",
            "parse_result": "parse_result",
        },
    )

    graph.add_edge("tools", "agent")
    graph.add_edge("parse_result", END)

    return graph.compile()


_compiled_graph = None


def get_graph():
    """Singleton accessor for the compiled graph."""
    global _compiled_graph
    if _compiled_graph is None:
        _compiled_graph = build_graph()
        logger.info("LangGraph support agent compiled successfully.")
    return _compiled_graph
