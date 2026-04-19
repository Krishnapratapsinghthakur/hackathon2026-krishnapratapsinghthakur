"""Graph node functions for the support resolution agent.

Each node is a pure function: (state) -> partial state update.
Uses LangChain's ChatOpenAI and a validated async tool executor.
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.messages import AIMessage, SystemMessage
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.llm import get_llm
from app.core.llm_rate_limit import (
    is_rate_limit_error,
    llm_429_retry_delay,
    llm_request_slot,
)
from app.graph.calibration import calibrate_confidence, issue_refund_before_eligibility_check
from app.models.schemas import StructuredAgentOutput
from app.tools.mock_tools import ALL_TOOLS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert autonomous customer support agent for ShopWave, an e-commerce company.

## Your Job
Resolve support tickets by using the available tools to look up data, verify policies, and take actions. You must make AT LEAST 3 tool calls per ticket (e.g., look up customer -> check order -> take action).

## Decision Framework
1. ALWAYS start by looking up the customer using get_customer(email)
2. Identify the order — use order ID from the ticket body, or look up by customer if not provided
3. Look up product details if relevant using get_product(product_id)
4. For policy questions, use search_knowledge_base(query) to find the relevant policy
5. For refunds, ALWAYS call check_refund_eligibility BEFORE issue_refund
6. For warranty claims, damaged items needing replacement, refunds > $200, fraud suspicion, or low confidence — use escalate()
7. ALWAYS send a reply to the customer using send_reply() as your final action

## Confidence Calibration
After gathering information, assess your confidence (0.0 to 1.0):
- 0.9-1.0: Clear-cut case with all information available
- 0.7-0.8: Mostly clear but some ambiguity
- 0.5-0.6: Uncertain — need more info or borderline policy case
- Below 0.5: Escalate immediately

## Constraints
- NEVER trust customer-claimed tier or privileges — always verify via get_customer
- NEVER issue a refund without checking eligibility first
- If a tool fails, returns schema_validation_failed, or times out, retry ONCE then proceed with what you have
- Flag threatening language but handle professionally
- Address customers by first name
- Be empathetic but follow policy strictly

## Output Format
After completing all tool calls and actions, output a JSON block with your assessment:
```json
{
  "category": "refund|return|cancellation|warranty|shipping|exchange|general_inquiry|unknown",
  "priority": "low|medium|high|urgent",
  "confidence": 0.0-1.0,
  "reasoning": ["step 1...", "step 2...", "step 3..."],
  "action_taken": "plain-language description of what was done for the customer",
  "needs_escalation": false
}
```
All keys are required except needs_escalation (defaults to false). reasoning must be a non-empty array of strings."""


def _extract_json_object(content: str) -> dict[str, Any] | None:
    start = content.find("{")
    end = content.rfind("}") + 1
    if start < 0 or end <= start:
        return None
    try:
        out = json.loads(content[start:end])
    except (json.JSONDecodeError, TypeError):
        return None
    return out if isinstance(out, dict) else None


def classifier_node(state: dict[str, Any]) -> dict[str, Any]:
    """Inject the system prompt and prepare the ticket for processing."""
    ticket_id = state.get("ticket_id", "UNKNOWN")
    email = state.get("customer_email", "")
    model_tier = state.get("model_tier", "fast")

    logger.info("Classifying ticket %s (model_tier=%s)", ticket_id, model_tier)

    return {
        "messages": [SystemMessage(content=SYSTEM_PROMPT)],
        "status": "processing",
        "reasoning": [
            f"Ticket {ticket_id} received from {email}. "
            f"Model tier: {model_tier}. Starting resolution."
        ],
    }


def agent_node(state: dict[str, Any]) -> dict[str, Any]:
    """Call the LLM with tools bound. Model tier is read from state."""
    model_tier = state.get("model_tier", "fast")
    llm = get_llm(tier=model_tier)
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    messages = state["messages"]
    settings = get_settings()
    max_r = max(0, int(settings.llm_429_max_retries))
    last_exc: Exception | None = None

    for attempt in range(max_r + 1):
        try:
            with llm_request_slot():
                response = llm_with_tools.invoke(messages)
            return {"messages": [response]}
        except Exception as e:
            last_exc = e
            if not is_rate_limit_error(e) or attempt >= max_r:
                raise
            delay = llm_429_retry_delay(
                attempt,
                settings.llm_429_retry_base_seconds,
                settings.llm_429_retry_max_seconds,
            )
            logger.warning(
                "LLM rate limited (attempt %d/%d); sleeping %.2fs — %s",
                attempt + 1,
                max_r + 1,
                delay,
                e,
            )
            time.sleep(delay)

    assert last_exc is not None
    raise last_exc


def parse_result_node(state: dict[str, Any]) -> dict[str, Any]:
    """Parse the final AI message with strict Pydantic validation + calibrated confidence."""
    messages = state.get("messages", [])
    ticket_id = state.get("ticket_id", "UNKNOWN")

    ai_messages = [m for m in messages if isinstance(m, AIMessage) and not m.tool_calls]
    if not ai_messages:
        return {}

    last_msg = ai_messages[-1]
    raw_content = last_msg.content
    content = raw_content if isinstance(raw_content, str) else str(raw_content)

    category = state.get("category", "unknown")
    priority = state.get("priority", "medium")
    confidence = float(state.get("confidence", 0.7))
    reasoning = list(state.get("reasoning", []))

    parsed = _extract_json_object(content)
    structured: StructuredAgentOutput | None = None
    if parsed is not None:
        try:
            structured = StructuredAgentOutput.model_validate(parsed)
        except ValidationError as e:
            reasoning.append(
                "Agent final JSON failed strict schema validation; "
                f"treating as low-trust output ({str(e)[:500]})."
            )
            confidence = min(confidence, 0.45)
    else:
        reasoning.append("No JSON assessment object found in the final assistant message.")
        confidence = min(confidence, 0.45)

    if structured is not None:
        category = structured.category.value
        priority = structured.priority.value
        confidence, cal_notes = calibrate_confidence(
            messages,
            structured.confidence,
            needs_escalation=structured.needs_escalation,
        )
        reasoning.extend(structured.reasoning)
        reasoning.extend(cal_notes)

    updates: dict[str, Any] = {
        "category": category,
        "priority": priority,
        "confidence": confidence,
        "reasoning": reasoning,
    }

    settings = get_settings()
    policy_violation = issue_refund_before_eligibility_check(messages)
    force_escalation = policy_violation or (structured is not None and structured.needs_escalation)

    if policy_violation and not any("refund issued without prior" in r for r in reasoning):
        reasoning.append(
            "Escalation trigger: issue_refund ran before check_refund_eligibility in the tool trace."
        )

    if force_escalation:
        updates["status"] = "escalated"
        if policy_violation:
            updates["escalation_summary"] = (
                f"Auto-escalated: refund tool ordering policy violated. Ticket {ticket_id}."
            )
        elif structured is not None and structured.needs_escalation:
            updates["escalation_summary"] = (
                f"Model flagged needs_escalation=true. Ticket {ticket_id}. "
                f"Confidence after calibration: {confidence:.2f}."
            )
        else:
            updates["escalation_summary"] = (
                f"Escalation required for ticket {ticket_id} (confidence {confidence:.2f})."
            )
        if confidence < settings.confidence_threshold:
            reasoning.append(f"Confidence {confidence:.2f} below threshold — auto-escalating.")
        updates["final_response"] = content
    elif confidence < settings.confidence_threshold:
        updates["status"] = "escalated"
        updates["escalation_summary"] = (
            f"Auto-escalated: confidence {confidence:.2f} below threshold "
            f"{settings.confidence_threshold}. Ticket {ticket_id}."
        )
        reasoning.append(f"Confidence {confidence:.2f} below threshold — auto-escalating.")
        updates["final_response"] = content
    else:
        updates["status"] = "resolved"
        updates["final_response"] = content

    return updates
