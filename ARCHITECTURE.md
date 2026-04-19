# ShopWave Architecture

> Production-grade autonomous support resolution agent.
> This document covers every layer of the system — from the HTTP edge to the database floor.

---

## Table of Contents

- [System Overview](#system-overview)
- [High-Level Architecture](#high-level-architecture)
- [Request Lifecycle](#request-lifecycle)
- [Backend — FastAPI](#backend--fastapi)
  - [API Layer](#api-layer)
  - [Security & Middleware](#security--middleware)
  - [Ticket Processing Pipeline](#ticket-processing-pipeline)
  - [LangGraph Agent (ReAct Loop)](#langgraph-agent-react-loop)
  - [Smart Model Router](#smart-model-router)
  - [LLM Factory (Multi-Provider)](#llm-factory-multi-provider)
  - [Tool System](#tool-system)
  - [Confidence Calibration](#confidence-calibration)
  - [Audit & Transparency](#audit--transparency)
  - [Cost Tracking](#cost-tracking)
- [Celery — Background Workers](#celery--background-workers)
- [Redis — Caching & Message Broker](#redis--caching--message-broker)
- [PostgreSQL — Persistent Storage](#postgresql--persistent-storage)
- [Frontend — Next.js](#frontend--nextjs)
- [Docker & Deployment](#docker--deployment)
- [Observability](#observability)
- [Error Handling & Resilience](#error-handling--resilience)
- [Production Readiness Checklist](#production-readiness-checklist)

---

## System Overview

```
                     ┌──────────────────────────────┐
                     │        Next.js Frontend       │
                     │      (React 19 + Tailwind)    │
                     │         localhost:3000         │
                     └──────────────┬───────────────┘
                                    │ HTTP / REST
                     ┌──────────────▼───────────────┐
                     │       FastAPI Backend         │
                     │         localhost:8000         │
                     │                               │
                     │  ┌─────────────────────────┐  │
                     │  │  Security Middleware     │  │
                     │  │  API Key · Rate Limit   │  │
                     │  │  CORS · Request ID      │  │
                     │  └───────────┬─────────────┘  │
                     │              │                 │
                     │  ┌───────────▼─────────────┐  │
                     │  │   Ticket Processor      │  │
                     │  │   Validation · Routing  │  │
                     │  │   Retry · DLQ           │  │
                     │  └───────────┬─────────────┘  │
                     │              │                 │
                     │  ┌───────────▼─────────────┐  │
                     │  │   LangGraph Agent       │  │
                     │  │   classify → agent ↔    │  │
                     │  │   tools → parse_result  │  │
                     │  └───────────┬─────────────┘  │
                     │              │                 │
                     │  ┌───────────▼─────────────┐  │
                     │  │   LLM Factory           │  │
                     │  │   Groq · OpenAI ·       │  │
                     │  │   Anthropic · Google ·   │  │
                     │  │   Ollama                 │  │
                     │  └─────────────────────────┘  │
                     └──────┬───────────┬────────────┘
                            │           │
               ┌────────────▼──┐   ┌────▼────────────┐
               │    Redis      │   │   PostgreSQL     │
               │  Cache · MQ   │   │   (Supabase)     │
               │  :6379        │   │   8 tables        │
               └───────┬───────┘   └─────────────────┘
                       │
              ┌────────▼────────┐
              │  Celery Worker  │
              │  Async tickets  │
              │  Batch jobs     │
              └─────────────────┘
```

---

## High-Level Architecture

The system follows a **layered, event-driven architecture** with clear separation of concerns:

| Layer | Responsibility | Technology |
|-------|---------------|------------|
| **Edge** | HTTP routing, auth, rate limiting | FastAPI + SlowAPI |
| **Processing** | Validation, routing, retry, DLQ | Custom async processor |
| **Orchestration** | LLM agent loop with tool execution | LangGraph (ReAct) |
| **Intelligence** | Multi-provider LLM calls | LangChain + Groq/OpenAI/Anthropic/Google/Ollama |
| **Persistence** | Domain data + operational data | PostgreSQL (asyncpg) |
| **Cache** | Hot data + result caching | Redis (aioredis) |
| **Workers** | Background ticket processing | Celery + Redis broker |
| **Frontend** | Operator console | Next.js 16 + React 19 + Tailwind 4 |

---

## Request Lifecycle

A ticket flows through the system in this exact order:

```
1.  HTTP Request arrives at FastAPI
2.  Security middleware: API key check + rate limit + request ID injection
3.  Pydantic v2 schema validation (email format, non-empty body, etc.)
4.  Pre-flight validation (duplicate detection, source check)
5.  Decision: sync or async (Celery)?
    ├── Sync:  process in-process, block until done
    └── Async: dispatch to Celery, return task_id for polling
6.  Customer pre-fetch from Postgres (with Redis cache-aside)
7.  Order pre-fetch for context enrichment
8.  Smart model routing: heuristic scan → fast or power tier
9.  LangGraph invocation:
    a. classify  → inject system prompt + ticket context
    b. agent     → LLM call with bound tools
    c. tools     → validated tool execution (Pydantic schema per tool)
    d. (loop b↔c until LLM stops calling tools)
    e. parse_result → extract JSON, Pydantic-validate, calibrate confidence
10. Confidence calibration (evidence count, policy violation detection)
11. Cost tracking (token estimation, per-model pricing)
12. Audit entry finalized (tool calls, reasoning trace, final response)
13. Result cached in Redis (10 min TTL)
14. Result persisted to Postgres
15. HTTP response returned to client
```

---

## Backend — FastAPI

### API Layer

Four route groups, each in its own file under `app/api/routes/`:

| Route | File | Purpose |
|-------|------|---------|
| `GET /health` | `health.py` | System status: DB mode, cache status, LLM config |
| `POST /tickets/process` | `tickets.py` | Single ticket (sync or `?async=true` for Celery) |
| `POST /tickets/batch` | `tickets.py` | Batch processing with bounded concurrency |
| `POST /tickets/quick` | `tickets.py` | Minimal input (email + message) — auto-generates ID/subject |
| `GET /tickets/status/{id}` | `tickets.py` | Celery task polling |
| `GET /tickets/result/{id}` | `tickets.py` | Cached result retrieval (Redis) |
| `GET /tickets/sample` | `tickets.py` | List all seeded sample tickets |
| `GET /audit` | `audit.py` | Full audit trail |
| `GET /audit/{ticket_id}` | `audit.py` | Per-ticket audit detail |
| `GET /audit/dlq` | `audit.py` | Dead-letter queue |
| `GET /settings` | `settings.py` | Current LLM configuration |
| `GET /settings/models` | `settings.py` | All supported models + pricing |
| `GET /settings/costs` | `settings.py` | Token usage + cost breakdown |

Interactive API docs: `/docs` (Swagger) and `/redoc` (ReDoc).

### Security & Middleware

Every request passes through these layers in order:

```
Request → CORS → Rate Limiter → Request ID → API Key Auth → Route Handler
```

| Component | Implementation | Details |
|-----------|---------------|---------|
| **CORS** | `CORSMiddleware` | Configurable origins via `CORS_ORIGINS` env var |
| **Rate Limiting** | SlowAPI (token bucket) | `30/min` single tickets, `5/min` batch, `60/min` global |
| **Request ID** | Custom middleware | `X-Request-ID` header (passed through or generated UUID) |
| **API Key** | `X-API-Key` header | Optional — disabled when `API_KEY` is empty (dev mode) |
| **Input Validation** | Pydantic v2 | Email regex, non-empty body, ticket_id format |
| **Exception Handlers** | Centralized | `TicketValidationError` (422), `TicketNotFoundError` (404), catch-all (500) |

### Ticket Processing Pipeline

`app/services/processor.py` — the core orchestrator.

**Pre-flight validation** (`app/services/validator.py`):
- Duplicate ticket_id detection (in-memory set with async lock)
- Source validation (email, chat, phone, api, ticket_queue)
- Body length warning for ultra-short tickets

**Context enrichment** (before LLM):
- Customer lookup by email (Postgres → Redis cache-aside)
- Order history fetch for the customer
- Pre-formatted context block injected into the prompt

**Retry with exponential backoff**:
- Configurable max retries (`MAX_RETRIES`, default 3)
- Backoff formula: `base^attempt` seconds (`RETRY_BACKOFF_BASE`, default 2.0)
- Each failure is audit-logged

**Dead-letter queue (DLQ)**:
- Tickets that exhaust all retries are sent to DLQ
- DLQ persisted to Postgres table `dead_letter_queue`
- Accessible via `GET /audit/dlq`
- Ticket ID released for potential reprocessing

**Bounded concurrency** (batch mode):
- `asyncio.Semaphore(MAX_CONCURRENT_TICKETS)` — default 10
- `asyncio.gather` for parallel execution within the bound

### LangGraph Agent (ReAct Loop)

`app/graph/` — the AI decision engine.

**Graph topology:**

```
  ┌─────────┐     ┌─────────┐     ┌─────────┐     ┌──────────────┐
  │ classify │ ──▶ │  agent  │ ──▶ │  tools  │     │ parse_result │
  └─────────┘     └────┬────┘     └────┬────┘     └──────────────┘
                       │               │                  ▲
                       │               └──────────────────┤
                       │                                  │
                       └──────────────────────────────────┘
                         (if no tool_calls → parse_result)
```

**Nodes:**

| Node | File | Responsibility |
|------|------|---------------|
| `classify` | `nodes.py` | Inject system prompt, set initial state |
| `agent` | `nodes.py` | LLM call with bound tools, 429 retry with backoff |
| `tools` | `validated_tools.py` | Execute tool calls, validate outputs with Pydantic |
| `parse_result` | `nodes.py` | Extract JSON from LLM output, validate with `StructuredAgentOutput`, calibrate confidence |

**State** (`app/graph/state.py`):

```python
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    ticket_id: str
    customer_email: str
    category: str           # refund | return | warranty | ...
    priority: str           # low | medium | high | urgent
    confidence: float       # 0.0 - 1.0, calibrated
    tool_call_log: list
    reasoning: list[str]    # step-by-step trace
    final_response: str
    escalation_summary: str
    status: str             # queued | processing | resolved | escalated | failed
    retry_count: int
    model_tier: str         # fast | power
    model_name: str
```

### Smart Model Router

`app/core/router.py` — zero-cost heuristic routing (no LLM call).

Runs **before** the LangGraph agent to decide which model tier to use:

| Signal | Detection Method | Route |
|--------|-----------------|-------|
| VIP/Premium customer | Customer tier from pre-fetch | **Power** |
| Threatening/legal language | Regex: `lawyer\|attorney\|legal action\|sue\|chargeback...` | **Power** |
| Fraud/social engineering | Regex: `premium member\|instant refund\|special policy...` | **Power** |
| High-value order (>$200) | Max order amount from pre-fetch | **Power** |
| Multiple orders (>2) | Order count from pre-fetch | **Power** |
| Vague ticket (<10 words) | Word count + keyword absence | **Power** |
| Standard ticket | None of the above | **Fast** |

Each routing decision produces human-readable reasons stored in the audit trail.

### LLM Factory (Multi-Provider)

`app/core/llm.py` — provider-agnostic model instantiation.

| Provider | Models | Cost |
|----------|--------|------|
| **Groq** | llama-3.3-70b-versatile | Free |
| **OpenAI** | gpt-4o-mini, gpt-4o, gpt-4.1-mini, gpt-4.1, gpt-4.1-nano | Paid |
| **Anthropic** | claude-3-haiku, claude-3.5-sonnet, claude-sonnet-4 | Paid |
| **Google** | gemini-2.0-flash, gemini-2.5-pro | Paid |
| **Ollama** | Any local model | Free |

**Environment presets** — one env var switches everything:

```
ENVIRONMENT=development  →  Groq (llama-3.3-70b)     $0.00
ENVIRONMENT=production   →  OpenAI (gpt-4o-mini/4o)   Paid
```

**LLM rate limiting** (`app/core/llm_rate_limit.py`):
- Process-wide bounded semaphore (`LLM_MAX_CONCURRENT_CALLS`, default 3)
- Sliding window RPM gate (`LLM_MAX_REQUESTS_PER_MINUTE`, default 28)
- Minimum interval between starts (`LLM_MIN_INTERVAL_SECONDS`, default 50ms)
- 429 retry with exponential backoff + jitter (configurable retries, base, cap)
- Thread-safe for sync LangGraph nodes

### Tool System

`app/tools/` — LangChain-compatible tools the agent can invoke.

**Available tools:**

| Tool | Type | Purpose |
|------|------|---------|
| `get_customer(email)` | Read | Look up customer by email |
| `get_order(order_id)` | Read | Look up order details |
| `get_product(product_id)` | Read | Look up product metadata |
| `search_knowledge_base(query)` | Read | Search company policies |
| `check_refund_eligibility(order_id)` | Read | Mandatory gate before refund |
| `issue_refund(order_id, amount)` | Write | Execute refund (irreversible) |
| `send_reply(ticket_id, message)` | Write | Send customer response |
| `escalate(ticket_id, summary, priority)` | Write | Hand off to human agent |

**Tool output validation** (`app/tools/output_validation.py`):
- Every tool output is parsed and validated against a Pydantic schema
- Invalid outputs are replaced with a controlled error envelope (`schema_validation_failed`)
- The LLM never sees raw, unvalidated data

**Failure injection** (configurable):
- `MOCK_TOOL_FAILURE_RATE` (default 5%) — random `TimeoutError` to exercise retries
- Set to 0 for stable demos or production

**Transparency layer** (`app/tools/transparency.py`):
- Every tool call gets a human-readable `why` field
- Explains the business purpose of the tool in the audit trail

### Confidence Calibration

`app/graph/calibration.py` — post-hoc confidence adjustment.

The LLM self-reports confidence, but the system **overrides** it based on evidence:

| Rule | Effect |
|------|--------|
| `issue_refund` called before `check_refund_eligibility` | Cap confidence at 0.55, force escalation |
| High confidence (>0.85) with <2 verified evidence reads | Cap at 0.72 |
| Model requested `needs_escalation=true` | Cap at 0.65 |
| No valid JSON in final output | Cap at 0.45 |
| Confidence below threshold (default 0.6) | Auto-escalate |

This prevents the LLM from being overconfident when it hasn't gathered enough evidence.

### Audit & Transparency

`app/services/audit.py` — every decision is logged.

**Write-through pattern**: in-memory (fast reads) + Postgres (durability). If Postgres is unavailable, in-memory still works.

Each audit entry captures:
- Ticket ID, status, category, priority
- Confidence score (raw + calibrated)
- Full tool call trace (inputs, outputs, errors, and `why` explanation)
- Step-by-step reasoning trace
- Final customer-facing response
- Escalation summary (if applicable)
- Error details (if failed)
- Timestamps (started, completed)
- Retry count

### Cost Tracking

`app/services/cost_tracker.py` — token-level financial observability.

- Estimates tokens from message history (~4 chars/token heuristic)
- Applies per-model pricing from the cost table
- Tracks per-ticket: input tokens, output tokens, LLM calls, tool calls, estimated USD cost
- Aggregates: total cost, by-model breakdown, by-tier breakdown
- Persisted to `cost_tracking` table in Postgres
- Accessible via `GET /settings/costs`

---

## Celery — Background Workers

`app/core/celery_app.py` + `app/tasks/ticket_tasks.py`

**Architecture**: `FastAPI (web) → Celery task → LangGraph agent → Postgres + Redis`

The web process accepts tickets and returns a `task_id` immediately. The Celery worker picks up the task, runs the LLM graph, and stores the result. The client polls `/tickets/status/{task_id}`.

**Configuration:**

| Setting | Value | Purpose |
|---------|-------|---------|
| Broker | Redis DB 1 | Task queue |
| Backend | Redis DB 2 | Result storage |
| Serializer | JSON | Safe serialization |
| `task_acks_late` | `true` | Acknowledge after completion (crash safety) |
| `worker_prefetch_multiplier` | 1 | One task at a time per worker (LLM is the bottleneck) |
| `task_soft_time_limit` | 120s | Graceful timeout per ticket |
| `task_time_limit` | 180s | Hard kill |
| `result_expires` | 3600s | Auto-cleanup old results |

**Queue routing:**

| Task | Queue |
|------|-------|
| `process_ticket_task` | `tickets` |
| `process_batch_task` | `batch` |

**Retry policy**: Celery-level retries (max 2 for single, max 1 for batch) + application-level retries within the processor.

---

## Redis — Caching & Message Broker

`app/core/cache.py`

Redis serves two roles: **cache layer** and **Celery message broker**.

**Database allocation:**

| DB | Purpose |
|----|---------|
| `redis://…/0` | Application cache |
| `redis://…/1` | Celery broker (task queue) |
| `redis://…/2` | Celery result backend |

**Caching strategy (cache-aside pattern):**

| Data | TTL | Rationale |
|------|-----|-----------|
| Customer profiles | 5 min | Rarely changes, frequent reads |
| Product catalog | 10 min | Static reference data |
| Order details | 2 min | Can change (refund status updates) |
| Knowledge base | 30 min | Almost never changes |
| Ticket results | 10 min | Hot reads after resolution |
| Audit entries | 1 min | Write-heavy, need freshness |

**Key naming convention**: `cache:{entity}:{id}` (e.g., `cache:customer:C001`, `cache:order:ORD-1001`)

**Cache invalidation**: Write-through — after a write (e.g., refund issued), the relevant cache key is deleted. Next read re-fetches from Postgres.

**Graceful degradation**: If Redis is unavailable, the system continues with Postgres-only reads. No crash, no data loss — just slower.

---

## PostgreSQL — Persistent Storage

`app/db/postgres.py`

**Connection pool**: asyncpg with 2–10 connections, 30s command timeout.

**Schema** (8 tables):

### Domain Tables (seeded on first boot)

```
customers (10 records)
├── customer_id    TEXT PK
├── name, email (UNIQUE), phone, tier
├── member_since, total_orders, total_spent
├── address        JSONB
└── notes          TEXT

products (8 records)
├── product_id     TEXT PK
├── name, category, price
├── warranty_months, return_window_days
├── returnable     BOOLEAN
└── notes          TEXT

orders (15 records)
├── order_id       TEXT PK
├── customer_id    FK → customers
├── product_id     FK → products
├── quantity, amount, status
├── order_date, delivery_date, return_deadline
├── refund_status
└── notes          TEXT

tickets (20 sample records)
├── ticket_id      TEXT PK
├── customer_email, subject, body
├── source, created_at, tier
└── expected_action TEXT

knowledge_base (1 record)
├── id             SERIAL PK
├── content        TEXT (full policy document)
└── updated_at     TIMESTAMPTZ
```

### Operational Tables (populated at runtime)

```
ticket_audit
├── id             SERIAL PK
├── ticket_id      TEXT UNIQUE
├── status, category, priority, confidence
├── tool_calls     JSONB (full trace)
├── reasoning      JSONB (step-by-step)
├── final_response, escalation_summary, error
├── started_at, completed_at
└── retries        INTEGER

cost_tracking
├── id             SERIAL PK
├── ticket_id, model_used, model_tier
├── input_tokens, output_tokens, estimated_cost
├── llm_calls, tool_calls
└── created_at     TIMESTAMPTZ

dead_letter_queue
├── id             SERIAL PK
├── ticket_id, error, retries
└── created_at     TIMESTAMPTZ
```

**Indexes**: B-tree on `email`, `customer_id`, `product_id`, `ticket_id` across relevant tables.

**Seeding**: Idempotent — checks if `customers` table is empty before inserting. JSON fixtures loaded from `app/db/seed/`.

**Graceful fallback**: If `DATABASE_URL` is not set, the entire system runs in-memory using JSON file stores. Zero configuration required for local development.

---

## Frontend — Next.js

`frontend/` — operator console built with Next.js 16, React 19, Tailwind CSS 4.

**Pages:**

| Route | Purpose |
|-------|---------|
| `/` | Dashboard — system health, feature overview |
| `/tickets` | Ticket deck — browse samples, process, view results |
| `/compose` | Quick compose — email + message → instant resolution |
| `/audit` | Audit log — full decision trail with tool call timeline |
| `/costs` | Cost dashboard — token usage, model breakdown |

**UI Components:**

| Component | Purpose |
|-----------|---------|
| `AppChrome` | Shell layout with scanlines + mesh background |
| `FloatingNav` | Glassmorphism navigation bar |
| `GlassPanel` | Frosted glass card with optional glow ring |
| `NeonButton` | Animated button with glow effects |
| `LinkGlow` | Navigation link with hover glow |
| `ResultModal` | Full-screen modal for ticket results |
| `ToolCallTimeline` | Visual timeline of agent tool invocations |
| `MeshBackground` | Animated gradient mesh |
| `Scanlines` | CRT-style scanline overlay |

**Tech stack:**

| Library | Version | Purpose |
|---------|---------|---------|
| Next.js | 16.2 | App Router, SSR, standalone output |
| React | 19.2 | UI framework |
| Tailwind CSS | 4.x | Utility-first styling |
| Framer Motion | 12.x | Animations and transitions |
| Lucide React | 1.x | Icon system |
| clsx + tailwind-merge | — | Conditional class merging |

---

## Docker & Deployment

### Container Architecture

```
docker-compose.yml
├── redis        (always on)     — redis:7-alpine, port 6379
├── api          (profile: full) — Python 3.12-slim, port 8000
└── web          (profile: full) — Node 20-alpine, port 3000
```

**Default mode**: `docker compose up -d` — starts only Redis (no port collision with local dev servers).

**Full stack**: `docker compose --profile full up --build -d` — Redis + API + Web.

### Backend Dockerfile

- Base: `python:3.12-slim`
- Non-root user: `appuser`
- Health check: `curl http://localhost:8000/health` every 30s
- Single Uvicorn worker (LLM calls are I/O-bound, not CPU-bound)

### Frontend Dockerfile

- Multi-stage build: `deps` → `builder` → `runner`
- Standalone Next.js output (no `node_modules` in production)
- Non-root user: `nextjs`
- Build-time arg: `NEXT_PUBLIC_API_URL`

### Platform Deployment

**Railway / Render**: Two services from the same repo:
1. API service — Root Directory: `backend`, Start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
2. Web service — Root Directory: `frontend`, Build/Start per platform docs
3. Set `NEXT_PUBLIC_API_URL` on the web service to the API's public URL

---

## Observability

### Structured Logging

`app/core/logging.py`

| Environment | Format |
|-------------|--------|
| Development | `%(asctime)s \| %(levelname)-8s \| %(name)s \| %(message)s` |
| Production | JSON: `{"ts":"…","level":"…","logger":"…","msg":"…"}` |

Noisy libraries (`httpx`, `httpcore`, `openai`) are suppressed to WARNING.

### Request Tracing

- Every response includes `X-Request-ID` header
- Client can pass their own via request header, or the system generates a UUID
- Request ID propagated via `contextvars.ContextVar` for async-safe correlation

### Audit Trail

- Every ticket produces a full audit entry in Postgres
- Tool calls logged with inputs, outputs, errors, and business rationale
- Reasoning steps captured at every decision point
- Available via REST API (`/audit`, `/audit/{ticket_id}`)

### Cost Monitoring

- Per-ticket token breakdown (input, output, total)
- Per-model and per-tier aggregation
- Estimated USD cost based on published pricing
- Available via REST API (`/settings/costs`)

---

## Error Handling & Resilience

### Graceful Degradation Matrix

| Component Down | System Behavior |
|----------------|----------------|
| **PostgreSQL** | Falls back to in-memory JSON stores. All features work, data lost on restart. |
| **Redis** | Caching disabled. No Celery workers. Sync processing only. No data loss. |
| **Celery** | Async dispatch fails silently, falls back to sync processing. |
| **LLM provider** | 429 retry with exponential backoff + jitter. Exhaustion → DLQ. |
| **Individual tool** | Tool returns error envelope. Agent retries once, then proceeds with partial data. |

### Retry Strategy

```
Application level:  MAX_RETRIES (3) × backoff(2^attempt)
LLM 429 level:      LLM_429_MAX_RETRIES (6) × backoff(1.5 × 2^attempt + jitter, cap 45s)
Celery level:       max_retries (2 single, 1 batch) × delay(5s)
```

### Dead-Letter Queue

Tickets that exhaust all retries are:
1. Logged with error details and retry count
2. Persisted to `dead_letter_queue` table
3. Ticket ID released for potential reprocessing
4. Accessible via `GET /audit/dlq`

---

## Production Readiness Checklist

This is what separates ShopWave from a tutorial project:

| Category | Feature | Status |
|----------|---------|--------|
| **Security** | API key authentication | Done |
| | Rate limiting (per-endpoint) | Done |
| | CORS with configurable origins | Done |
| | Request ID correlation | Done |
| | Pydantic input validation | Done |
| | No hardcoded secrets | Done |
| | Non-root Docker containers | Done |
| **Reliability** | Exponential backoff retry | Done |
| | Dead-letter queue | Done |
| | Graceful degradation (DB/Redis/Celery down) | Done |
| | LLM 429 rate limit handling | Done |
| | Process-wide concurrency throttling | Done |
| | Duplicate ticket detection | Done |
| | Celery `task_acks_late` (crash safety) | Done |
| | Celery time limits (soft + hard kill) | Done |
| **Observability** | Structured JSON logging (production) | Done |
| | Full audit trail per ticket | Done |
| | Tool call transparency (why each tool exists) | Done |
| | Cost tracking per ticket | Done |
| | Request ID tracing | Done |
| | Health check endpoint | Done |
| | Docker HEALTHCHECK | Done |
| **Architecture** | Async-first (asyncio + asyncpg + aioredis) | Done |
| | Background workers (Celery) | Done |
| | Cache-aside with multi-tier TTL | Done |
| | Connection pooling (asyncpg 2-10) | Done |
| | Bounded concurrency (semaphore) | Done |
| | Multi-provider LLM factory | Done |
| | Smart model routing (cost optimization) | Done |
| | Confidence calibration (evidence-based) | Done |
| | Tool output schema validation | Done |
| | Idempotent database seeding | Done |
| **Deployment** | Docker Compose (dev + full stack) | Done |
| | Multi-stage Docker builds (frontend) | Done |
| | Separate deploy roots (backend/frontend) | Done |
| | Environment-based config (dev/prod presets) | Done |
| | Railway/Render deployment guide | Done |
| **Testing** | 51 tests (API, validation, routing, store, cost, security) | Done |
| | pytest + pytest-asyncio | Done |

---

*This document reflects the system as built. Update it when architecture changes.*
