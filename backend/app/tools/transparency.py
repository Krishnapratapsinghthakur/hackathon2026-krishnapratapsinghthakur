"""Human-readable explanations for each LangChain tool — API + audit transparency."""

from __future__ import annotations

from typing import Any

from app.models.schemas import ToolCall

# What each tool is for (policy / ops). Shown to users with inputs & outputs.
_TOOL_PURPOSE: dict[str, str] = {
    "get_order": "Load authoritative order record (status, amounts, refund flags, dates) before changing money or promising outcomes.",
    "get_customer": "Confirm the shopper’s profile, tier, and history so decisions match account standing and VIP rules.",
    "get_product": "Read catalog metadata (return window, warranty, category) when policy depends on the SKU, not only the order row.",
    "search_knowledge_base": "Ground answers in written ShopWave policies (returns, refunds, escalation) instead of guessing.",
    "check_refund_eligibility": "Mandatory gate before any refund — validates timing, prior refunds, and shipment state.",
    "issue_refund": "Execute a financial credit after eligibility checks; irreversible, so only after verification.",
    "send_reply": "Deliver the final customer-facing message for this ticket through the support channel.",
    "escalate": "Hand off to a human when automation limits are hit (high value, fraud signals, warranty edge cases, low confidence).",
}


def explain_tool_call(tool_name: str, arguments: dict[str, Any]) -> str:
    """Static rationale for *why this class of tool exists*; args add concrete targets."""
    base = _TOOL_PURPOSE.get(
        tool_name,
        "Agent invoked a tool to read data or perform a governed action in the support playbook.",
    )
    bits: list[str] = []
    if oid := arguments.get("order_id"):
        bits.append(f"order `{oid}`")
    if em := arguments.get("email"):
        bits.append(f"customer `{em}`")
    if pid := arguments.get("product_id"):
        bits.append(f"product `{pid}`")
    if tid := arguments.get("ticket_id"):
        bits.append(f"ticket `{tid}`")
    if q := arguments.get("query"):
        qstr = str(q).strip()
        if len(qstr) > 80:
            qstr = qstr[:77] + "…"
        bits.append(f"query “{qstr}”")
    if amt := arguments.get("amount"):
        bits.append(f"amount `{amt}`")
    if pri := arguments.get("priority"):
        bits.append(f"priority `{pri}`")
    if bits:
        return f"{base} Targeting: {', '.join(bits)}."
    return base


def tool_call_from_extracted(d: dict[str, Any]) -> ToolCall:
    """Build an auditable ToolCall including transparency text."""
    name = d["tool_name"]
    args = d.get("arguments") if isinstance(d.get("arguments"), dict) else {}
    return ToolCall(
        tool_name=name,
        arguments=args,
        result=d.get("result"),
        error=d.get("error"),
        why=explain_tool_call(name, args),
    )
