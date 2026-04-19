from __future__ import annotations

import enum
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Enums ──────────────────────────────────────────────────────

class TicketStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    FAILED = "failed"


class Priority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class TicketCategory(str, enum.Enum):
    REFUND = "refund"
    RETURN = "return"
    CANCELLATION = "cancellation"
    WARRANTY = "warranty"
    SHIPPING = "shipping"
    EXCHANGE = "exchange"
    GENERAL_INQUIRY = "general_inquiry"
    UNKNOWN = "unknown"


# ── Inbound ticket ─────────────────────────────────────────────

class TicketInput(BaseModel):
    ticket_id: str = Field(..., min_length=1)
    customer_email: str = Field(..., min_length=3)
    subject: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)
    source: str = "email"
    created_at: datetime | None = None
    tier: int = 1

    @field_validator("customer_email")
    @classmethod
    def validate_email_format(cls, v: str) -> str:
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(pattern, v):
            raise ValueError(f"Invalid email format: '{v}'")
        return v.lower().strip()

    @field_validator("ticket_id")
    @classmethod
    def validate_ticket_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("ticket_id cannot be blank")
        return v.strip()

    @field_validator("body")
    @classmethod
    def validate_body_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Ticket body cannot be blank")
        return v


# ── Quick ticket input (minimal — for UI) ─────────────────────

class QuickTicketInput(BaseModel):
    """Minimal input for the UI — just email + message. Everything else is auto-generated."""
    customer_email: str = Field(..., min_length=3)
    message: str = Field(..., min_length=5)
    source: str = "web_ui"

    @field_validator("customer_email")
    @classmethod
    def validate_email_format_quick(cls, v: str) -> str:
        pattern = r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$"
        if not re.match(pattern, v):
            raise ValueError(f"Invalid email format: '{v}'")
        return v.lower().strip()

    @field_validator("message")
    @classmethod
    def validate_message_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("Message cannot be blank")
        return v


# ── Tool I/O schemas ──────────────────────────────────────────

class StructuredAgentOutput(BaseModel):
    """Strict schema for the final JSON block the agent must emit (post-tool loop)."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    category: TicketCategory
    priority: Priority
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: list[str] = Field(min_length=1, max_length=50)
    action_taken: str = Field(min_length=1, max_length=20000)
    needs_escalation: bool = False

    @field_validator("category", mode="before")
    @classmethod
    def coerce_category(cls, v: Any) -> Any:
        if isinstance(v, TicketCategory):
            return v
        if v is None or (isinstance(v, str) and not v.strip()):
            return TicketCategory.UNKNOWN
        s = str(v).lower().strip().replace(" ", "_").replace("-", "_")
        for cat in TicketCategory:
            if cat.value == s:
                return cat
        return TicketCategory.UNKNOWN

    @field_validator("priority", mode="before")
    @classmethod
    def coerce_priority(cls, v: Any) -> Any:
        if isinstance(v, Priority):
            return v
        if v is None or (isinstance(v, str) and not v.strip()):
            return Priority.MEDIUM
        s = str(v).lower().strip()
        for p in Priority:
            if p.value == s:
                return p
        return Priority.MEDIUM


class CustomerInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    customer_id: str
    name: str
    email: str
    phone: str
    tier: str
    member_since: str
    total_orders: int
    total_spent: float
    address: dict[str, str]
    notes: str


class OrderInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    order_id: str
    customer_id: str
    product_id: str
    quantity: int
    amount: float
    status: str
    order_date: str
    delivery_date: str | None
    return_deadline: str | None
    refund_status: str | None
    notes: str


class ProductInfo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    product_id: str
    name: str
    category: str
    price: float
    warranty_months: int
    return_window_days: int
    returnable: bool
    notes: str


class RefundEligibility(BaseModel):
    model_config = ConfigDict(extra="ignore")

    eligible: bool
    reason: str
    order_id: str
    amount: float


class RefundResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    success: bool
    order_id: str
    amount: float
    message: str


class EscalationResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    escalated: bool
    ticket_id: str
    summary: str
    priority: str
    assigned_to: str


class ReplyResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    sent: bool
    ticket_id: str
    message: str


class KnowledgeBaseResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    query: str
    results: list[str]
    source: str


# ── Audit / Decision logging ─────────────────────────────────

class ToolCall(BaseModel):
    tool_name: str
    arguments: dict[str, Any]
    result: Any = None
    error: str | None = None
    why: str = Field(
        default="",
        description="Why this tool exists in the workflow (playbook + concrete targets).",
    )
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class AuditEntry(BaseModel):
    ticket_id: str
    status: TicketStatus
    category: TicketCategory | None = None
    priority: Priority | None = None
    confidence: float | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reasoning: list[str] = Field(default_factory=list)
    final_response: str | None = None
    escalation_summary: str | None = None
    error: str | None = None
    started_at: datetime = Field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    retries: int = 0


# ── API responses ─────────────────────────────────────────────

class TicketResult(BaseModel):
    ticket_id: str
    status: TicketStatus
    category: TicketCategory | None = None
    priority: Priority | None = None
    confidence: float | None = None
    response: str | None = None
    escalation_summary: str | None = None
    tool_calls_count: int = 0
    """Full tool trace: inputs, outputs, and why each tool is part of the playbook."""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    reasoning_steps: list[str] = Field(default_factory=list)
    model_used: str | None = None
    model_tier: str | None = None


class BatchRequest(BaseModel):
    tickets: list[TicketInput] = Field(default_factory=list)
    load_sample: bool = False


class BatchResponse(BaseModel):
    total: int
    results: list[TicketResult]
    processing_time_seconds: float
    dead_letter: list[dict[str, Any]] = Field(default_factory=list)
