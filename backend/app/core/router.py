"""Smart model tier router — decides fast vs power model per ticket.

This runs BEFORE the LangGraph agent. It uses simple heuristics (no LLM call)
to classify ticket complexity, so routing itself is free.

Routing logic:
  POWER model when:
    - Ticket tier >= 2 (premium/VIP customer)
    - Threatening/legal language detected
    - Refund amount likely > $200 (from pre-fetched orders)
    - Multiple orders involved
    - Ambiguous/vague ticket body
    - Fraud indicators
  FAST model for everything else.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal

from app.core.config import get_settings

logger = logging.getLogger(__name__)

ModelTier = Literal["fast", "power"]

THREAT_PATTERNS = re.compile(
    r"lawyer|attorney|legal\s+action|sue\s+you|dispute|chargeback|"
    r"report\s+you|bbb|consumer\s+protection|court",
    re.IGNORECASE,
)

FRAUD_PATTERNS = re.compile(
    r"premium\s+member|instant\s+refund|without\s+questions|"
    r"special\s+policy|immediate\s+refund|vip\s+policy",
    re.IGNORECASE,
)

VAGUE_INDICATORS = re.compile(
    r"^(hey|hi|hello|help|pls|please)?\s*(so\s+)?(the\s+)?thing",
    re.IGNORECASE,
)


def route_ticket(
    ticket_body: str,
    ticket_subject: str,
    customer_tier: str | None,
    order_amounts: list[float] | None = None,
    num_orders: int = 0,
) -> tuple[ModelTier, list[str]]:
    """Determine which model tier to use for a ticket.

    Returns (tier, reasons) where reasons explain why this tier was chosen.
    """
    settings = get_settings()

    if not settings.llm_smart_routing:
        default = settings.llm_default_tier
        tier: ModelTier = "power" if default == "power" else "fast"
        return tier, [f"Smart routing disabled. Using default tier: {default}"]

    reasons: list[str] = []
    combined_text = f"{ticket_subject} {ticket_body}"

    use_power = False

    if customer_tier and customer_tier.lower() in ("vip", "premium"):
        use_power = True
        reasons.append(f"Customer is {customer_tier.upper()} tier — using powerful model.")

    if THREAT_PATTERNS.search(combined_text):
        use_power = True
        reasons.append("Threatening/legal language detected — needs careful handling.")

    if FRAUD_PATTERNS.search(combined_text):
        use_power = True
        reasons.append("Potential social engineering/fraud indicators found.")

    if order_amounts:
        max_amount = max(order_amounts)
        if max_amount > 200:
            use_power = True
            reasons.append(f"High-value order (${max_amount:.2f}) — using powerful model.")

    if num_orders > 2:
        use_power = True
        reasons.append(f"Multiple orders ({num_orders}) — complex resolution needed.")

    body_words = len(ticket_body.strip().split())
    if body_words < 10 and not any(
        kw in ticket_body.lower()
        for kw in ("ord-", "order", "refund", "return", "cancel")
    ):
        use_power = True
        reasons.append(f"Vague ticket body ({body_words} words, no identifiers) — needs reasoning.")

    if VAGUE_INDICATORS.search(ticket_body):
        use_power = True
        reasons.append("Vague/informal language — needs stronger comprehension.")

    if not use_power:
        reasons.append("Standard ticket — using fast/cheap model.")

    tier = "power" if use_power else "fast"

    logger.info(
        "Model routing: tier=%s reasons=%s",
        tier, "; ".join(reasons),
    )
    return tier, reasons
