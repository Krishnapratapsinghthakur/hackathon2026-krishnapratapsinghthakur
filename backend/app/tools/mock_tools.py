"""
LangChain-compatible tool definitions with realistic failure modes.

Each tool is an async coroutine wrapped with @tool from langchain_core.
Failure injection: random timeouts, malformed data, missing fields
to satisfy the constraint "at least one tool will timeout or return malformed data."
"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from datetime import datetime, timedelta
from typing import Any

from langchain_core.tools import tool

from app.db import store

logger = logging.getLogger(__name__)


def _failure_rate() -> float:
    from app.core.config import get_settings

    return get_settings().mock_tool_failure_rate


def _maybe_fail(tool_name: str) -> None:
    """Randomly raise TimeoutError to exercise retries / DLQ (rate from MOCK_TOOL_FAILURE_RATE).

    The error text says 'after 30 s' for realism; there is no actual 30 second sleep.
    """
    rate = _failure_rate()
    if rate <= 0:
        return
    if random.random() < rate:
        raise TimeoutError(f"{tool_name}: upstream service timed out after 30 s")


def _format(data: Any) -> str:
    if data is None:
        return json.dumps({"error": "not_found", "message": "No matching record found."})
    if isinstance(data, (dict, list)):
        return json.dumps(data, default=str)
    return str(data)


# ── READ / LOOKUP TOOLS ───────────────────────────────────────


@tool
async def get_order(order_id: str) -> str:
    """Look up an order by its order ID (e.g. ORD-1001). Returns order details including status, dates, amount, and refund status."""
    _maybe_fail("get_order")
    order = await store.get_order(order_id)
    if order is None:
        return json.dumps({
            "error": "order_not_found",
            "message": f"No order found with ID '{order_id}'. Please verify the order ID.",
        })
    return _format(order)


@tool
async def get_customer(email: str) -> str:
    """Look up a customer by their email address. Returns customer profile, tier, total orders, spending history, and internal notes."""
    _maybe_fail("get_customer")
    customer = await store.get_customer_by_email(email)
    if customer is None:
        return json.dumps({
            "error": "customer_not_found",
            "message": f"No customer found with email '{email}'. The email may not be registered.",
        })
    return _format(customer)


@tool
async def get_product(product_id: str) -> str:
    """Look up product metadata by product ID (e.g. P001). Returns product name, category, price, warranty, return window, and return policy notes."""
    _maybe_fail("get_product")
    product = await store.get_product(product_id)
    if product is None:
        return json.dumps({
            "error": "product_not_found",
            "message": f"No product found with ID '{product_id}'.",
        })
    return _format(product)


@tool
async def search_knowledge_base(query: str) -> str:
    """Search ShopWave's internal knowledge base for policy and FAQ information. Use for questions about return policy, refund policy, warranty, exchanges, escalation guidelines, and customer tiers."""
    _maybe_fail("search_knowledge_base")
    kb = await store.get_knowledge_base()
    query_lower = query.lower()
    sections = kb.split("\n## ")
    relevant: list[str] = []

    keywords_to_sections = {
        "return": ["Return Policy", "Exchange Policy", "Common FAQs"],
        "refund": ["Refund Policy", "Common FAQs"],
        "warranty": ["Warranty Policy"],
        "cancel": ["Order Cancellation Policy"],
        "exchange": ["Exchange Policy"],
        "escalat": ["Escalation Guidelines"],
        "tier": ["Customer Tiers", "Refund Policy"],
        "vip": ["Customer Tiers", "Refund Policy"],
        "premium": ["Customer Tiers", "Refund Policy"],
        "damage": ["Return Policy", "Common FAQs"],
        "defect": ["Return Policy", "Warranty Policy"],
        "ship": ["Order Cancellation Policy"],
        "tone": ["Tone & Communication Guidelines"],
    }

    matched_section_titles: set[str] = set()
    for kw, titles in keywords_to_sections.items():
        if kw in query_lower:
            matched_section_titles.update(titles)

    for section in sections:
        title_line = section.split("\n", 1)[0].strip().replace("#", "").strip()
        if any(t.lower() in title_line.lower() for t in matched_section_titles):
            relevant.append(section.strip())

    if not relevant:
        for section in sections:
            if any(word in section.lower() for word in query_lower.split()):
                relevant.append(section.strip())

    if not relevant:
        return json.dumps({
            "query": query,
            "results": ["No matching policy information found. Try a more specific query."],
            "source": "knowledge_base",
        })

    return json.dumps({
        "query": query,
        "results": relevant[:3],
        "source": "knowledge_base",
    })


# ── WRITE / ACT TOOLS ────────────────────────────────────────


@tool
async def check_refund_eligibility(order_id: str) -> str:
    """Check whether an order is eligible for a refund. Returns eligibility status and reason. MUST be called before issue_refund. May throw errors for invalid orders."""
    _maybe_fail("check_refund_eligibility")

    order = await store.get_order(order_id)
    if order is None:
        return json.dumps({
            "error": "order_not_found",
            "eligible": False,
            "reason": f"Order '{order_id}' does not exist in our system.",
            "order_id": order_id,
            "amount": 0,
        })

    if order.get("refund_status") == "refunded":
        return json.dumps({
            "eligible": False,
            "reason": "This order has already been refunded.",
            "order_id": order_id,
            "amount": order["amount"],
        })

    if order["status"] == "processing":
        return json.dumps({
            "eligible": False,
            "reason": "Order is still processing. Recommend cancellation instead of refund.",
            "order_id": order_id,
            "amount": order["amount"],
        })

    if order["status"] == "shipped":
        return json.dumps({
            "eligible": False,
            "reason": "Order is currently in transit. Cannot refund until delivered.",
            "order_id": order_id,
            "amount": order["amount"],
        })

    return_deadline_str = order.get("return_deadline")
    if return_deadline_str:
        return_deadline = datetime.strptime(return_deadline_str, "%Y-%m-%d")
        ticket_date = datetime(2024, 3, 15)
        if ticket_date > return_deadline:
            product = await store.get_product(order["product_id"])
            warranty_months = product.get("warranty_months", 0) if product else 0
            if warranty_months > 0:
                delivery_date = datetime.strptime(order["delivery_date"], "%Y-%m-%d")
                warranty_end = delivery_date + timedelta(days=warranty_months * 30)
                if ticket_date <= warranty_end:
                    return json.dumps({
                        "eligible": False,
                        "reason": f"Return window expired on {return_deadline_str}. However, warranty is active until {warranty_end.strftime('%Y-%m-%d')}. Recommend escalating as warranty claim.",
                        "order_id": order_id,
                        "amount": order["amount"],
                    })
            return json.dumps({
                "eligible": False,
                "reason": f"Return window expired on {return_deadline_str}.",
                "order_id": order_id,
                "amount": order["amount"],
            })

    return json.dumps({
        "eligible": True,
        "reason": "Order is within the return window and eligible for refund.",
        "order_id": order_id,
        "amount": order["amount"],
    })


@tool
async def issue_refund(order_id: str, amount: float) -> str:
    """Issue a refund for a given order. This is IRREVERSIBLE — you MUST call check_refund_eligibility first and confirm eligibility before calling this tool. Requires both order_id and refund amount."""
    _maybe_fail("issue_refund")

    order = await store.get_order(order_id)
    if order is None:
        return json.dumps({
            "success": False,
            "order_id": order_id,
            "amount": amount,
            "message": f"Cannot issue refund: order '{order_id}' not found.",
        })

    if order.get("refund_status") == "refunded":
        return json.dumps({
            "success": False,
            "order_id": order_id,
            "amount": amount,
            "message": "Refund already processed for this order.",
        })

    if amount > order["amount"]:
        return json.dumps({
            "success": False,
            "order_id": order_id,
            "amount": amount,
            "message": f"Refund amount ${amount} exceeds order amount ${order['amount']}.",
        })

    await store.update_order(order_id, {"refund_status": "refunded"})
    logger.info("Refund issued: order=%s amount=%.2f", order_id, amount)

    return json.dumps({
        "success": True,
        "order_id": order_id,
        "amount": amount,
        "message": f"Refund of ${amount:.2f} has been successfully issued for order {order_id}. Customer will receive the refund in 5-7 business days.",
    })


@tool
async def send_reply(ticket_id: str, message: str) -> str:
    """Send a response message to the customer for a given ticket. The message should be professional, empathetic, and use the customer's first name."""
    _maybe_fail("send_reply")

    logger.info("Reply sent: ticket=%s length=%d", ticket_id, len(message))
    return json.dumps({
        "sent": True,
        "ticket_id": ticket_id,
        "message": message,
    })


@tool
async def escalate(ticket_id: str, summary: str, priority: str) -> str:
    """Escalate a ticket to a human agent. Use when: warranty claims, replacement requests, fraud/social engineering, refund >$200, conflicting data, or agent confidence <0.6. Include a structured summary of the issue, what was verified, and recommended resolution. Priority must be one of: low, medium, high, urgent."""
    _maybe_fail("escalate")

    valid_priorities = {"low", "medium", "high", "urgent"}
    if priority.lower() not in valid_priorities:
        return json.dumps({
            "escalated": False,
            "ticket_id": ticket_id,
            "summary": summary,
            "priority": priority,
            "assigned_to": "",
            "error": f"Invalid priority '{priority}'. Must be one of: {', '.join(sorted(valid_priorities))}.",
        })

    assignment_map = {
        "low": "support-queue-l1",
        "medium": "support-queue-l2",
        "high": "supervisor-team",
        "urgent": "manager-on-call",
    }

    assigned = assignment_map[priority.lower()]
    logger.info("Escalated: ticket=%s priority=%s assigned=%s", ticket_id, priority, assigned)

    return json.dumps({
        "escalated": True,
        "ticket_id": ticket_id,
        "summary": summary,
        "priority": priority,
        "assigned_to": assigned,
    })


ALL_TOOLS = [
    get_order,
    get_customer,
    get_product,
    search_knowledge_base,
    check_refund_eligibility,
    issue_refund,
    send_reply,
    escalate,
]
