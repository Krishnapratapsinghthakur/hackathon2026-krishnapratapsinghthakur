# ShopWave Autonomous Support Resolution Agent

AI-powered customer support agent that ingests, classifies, and autonomously resolves support tickets using **LangGraph** orchestration, **Redis** caching, **Celery** background workers, and **Supabase Postgres** persistence.

> **Full architecture deep-dive**: [ARCHITECTURE.md](./ARCHITECTURE.md)

---

## What Makes This Production-Ready

This is not a tutorial project with a single `main.py`. Here is what separates it from typical LLM demos:

| Concern | Tutorial Project | ShopWave |
|---------|-----------------|----------|
| **Processing** | Sync, blocks on every LLM call | Celery workers for async dispatch, sync fallback |
| **Resilience** | Crashes on first error | 3-level retry (app + LLM 429 + Celery), dead-letter queue, graceful degradation |
| **Caching** | None | Redis cache-aside with 6 TTL tiers (2 min - 30 min) |
| **Database** | SQLite or none | Supabase Postgres with asyncpg pool (2-10), 8 tables, indexed |
| **Security** | Open endpoints | API key auth, rate limiting, CORS, request ID tracing, Pydantic validation |
| **LLM Management** | Single hardcoded model | 5 providers, smart cost-based routing, process-wide rate gate |
| **Observability** | `print()` statements | Structured JSON logging, full audit trail, tool transparency, cost tracking |
| **Validation** | Trust LLM output | Pydantic schema on every tool output, confidence calibration, policy violation detection |
| **Deployment** | `python app.py` | Docker Compose, multi-stage builds, non-root containers, health checks |
| **Cost Control** | Unknown spend | Token counting, per-model pricing, budget tracking, smart routing |
| **Failure Modes** | Untested | Configurable tool failure injection, duplicate detection, DLQ with Postgres persistence |

---

## Architecture at a Glance

```
  Next.js Frontend (:3000)
         |
    FastAPI Backend (:8000)
    |-- Security: API Key + Rate Limit + CORS + Request ID
    |-- Processor: Validation -> Routing -> Retry -> DLQ
    |-- LangGraph: classify -> agent <-> tools -> parse_result
    |-- LLM Factory: Groq | OpenAI | Anthropic | Google | Ollama
    +-- Audit + Cost Tracking
         |                    |
    Redis (:6379)        PostgreSQL
    |-- Cache (DB 0)     |-- 5 domain tables (seeded)
    |-- Celery MQ (DB 1) +-- 3 operational tables (runtime)
    +-- Results (DB 2)
         |
    Celery Worker
    +-- Background ticket processing
```

> Full diagrams, data flows, and table schemas: [ARCHITECTURE.md](./ARCHITECTURE.md)

---

## Monorepo Layout

| Path | Role | Default Port |
|------|------|:------------:|
| `backend/` | FastAPI + LangGraph + Celery + pytest | **8000** |
| `frontend/` | Next.js 16 + React 19 + Tailwind 4 | **3000** |
| `docker-compose.yml` | Shared Redis; optional `--profile full` for full stack | **6379** |

The two apps are separate packages (Python vs Node), independent ports, independent deploy roots.

---

## Quick Start

### 1. Backend (FastAPI)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set GROQ_API_KEY (free), optionally DATABASE_URL and REDIS_URL
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend (Next.js) — second terminal

```bash
cd frontend
cp env.sample .env.local   # NEXT_PUBLIC_API_URL=http://localhost:8000
npm install && npm run dev
# Open http://localhost:3000
```

### 3. Redis + Celery Worker (optional)

```bash
# Start Redis
docker compose up -d

# Start Celery worker (from backend/)
celery -A app.core.celery_app worker --loglevel=info --queues=tickets,batch
```

### 4. Tests

```bash
cd backend && PYTHONPATH=. pytest tests/ -v --tb=short
```

51 tests covering API routes, validation, smart routing, store, cost tracking, and security.

---

## Environment Configuration

```bash
# Development (Groq free tier - $0.00)
ENVIRONMENT=development
GROQ_API_KEY=gsk_your-key

# Production (OpenAI paid models)
ENVIRONMENT=production
OPENAI_API_KEY=sk-your-key
```

Just flip `ENVIRONMENT` — provider, models, and routing presets switch automatically. See `.env.example` for all options.

---

## API Endpoints

| Method | Endpoint | Description | Rate Limit |
|--------|----------|-------------|:----------:|
| `GET` | `/health` | System status, DB mode, LLM config | -- |
| `POST` | `/tickets/process` | Process single ticket (sync or `?async=true`) | 30/min |
| `POST` | `/tickets/batch` | Process batch with bounded concurrency | 5/min |
| `POST` | `/tickets/quick` | Minimal input: email + message | 30/min |
| `GET` | `/tickets/status/{task_id}` | Poll Celery task progress | -- |
| `GET` | `/tickets/result/{ticket_id}` | Cached result (Redis) | -- |
| `GET` | `/tickets/sample` | List seeded sample tickets | -- |
| `GET` | `/audit` | Full audit trail | -- |
| `GET` | `/audit/{ticket_id}` | Per-ticket audit detail | -- |
| `GET` | `/audit/dlq` | Dead-letter queue | -- |
| `GET` | `/settings` | Current LLM configuration | -- |
| `GET` | `/settings/models` | Supported models + pricing | -- |
| `GET` | `/settings/costs` | Token usage + cost breakdown | -- |
| `GET` | `/docs` | Swagger UI | -- |
| `GET` | `/redoc` | ReDoc | -- |

---

## Smart Model Routing

Zero-cost heuristic engine (no LLM call) that routes each ticket to the optimal model:

| Signal | Route |
|--------|-------|
| VIP/Premium customer | Power model |
| Threatening/legal language | Power model |
| Fraud/social engineering patterns | Power model |
| High-value order (>$200) | Power model |
| Vague ticket (<10 words, no IDs) | Power model |
| Multiple orders (>2) | Power model |
| Standard ticket | Fast model |

---

## Database Schema (8 Tables)

**Domain Data** (seeded automatically on first boot):
- `customers` — 10 customers with tiers, spend history, internal notes
- `products` — 8 products with warranty, return policies
- `orders` — 15 orders with status, dates, refund tracking
- `tickets` — 20 sample support tickets
- `knowledge_base` — Company policies (return, refund, warranty, escalation)

**Operational Data** (populated at runtime):
- `ticket_audit` — Full decision trace per ticket (tool calls, reasoning, response)
- `cost_tracking` — Token usage + estimated cost per ticket
- `dead_letter_queue` — Failed tickets after retry exhaustion

> Full schema with columns and indexes: [ARCHITECTURE.md](./ARCHITECTURE.md#postgresql--persistent-storage)

---

## Redis Caching Strategy

Cache-aside pattern with domain-specific TTLs:

| Data | TTL | Why |
|------|:---:|-----|
| Customer profiles | 5 min | Rarely changes, frequent reads |
| Product catalog | 10 min | Static reference data |
| Order details | 2 min | Can change (refund status) |
| Knowledge base | 30 min | Almost never changes |
| Ticket results | 10 min | Hot reads after resolution |
| Audit entries | 1 min | Write-heavy, need freshness |

If Redis is down, the system continues with Postgres-only reads. No crash, no data loss.

---

## Celery Background Workers

```
FastAPI (web) -> Celery task -> LangGraph agent -> Postgres + Redis
```

- **Broker**: Redis DB 1
- **Backend**: Redis DB 2
- **Crash safety**: `task_acks_late=true` — tasks acknowledged after completion
- **Time limits**: 120s soft / 180s hard per ticket
- **Queue routing**: `tickets` queue for single, `batch` queue for batch
- **Fallback**: If Celery is unavailable, requests process synchronously

---

## Security

| Feature | Implementation |
|---------|---------------|
| API Key Auth | `X-API-Key` header (optional — disabled when empty) |
| Rate Limiting | SlowAPI: 30/min single, 5/min batch, 60/min global |
| CORS | Configurable origins via `CORS_ORIGINS` |
| Request Tracing | `X-Request-ID` on every response |
| Input Validation | Pydantic v2 validators (email, body, ticket_id) |
| No Hardcoded Secrets | All config via environment variables |
| Non-Root Containers | Both Docker images run as unprivileged users |
| Tool Output Validation | Pydantic schema per tool — LLM never sees invalid data |

---

## Deployment

### Docker Compose

```bash
# Redis only (default — no port collision with local dev)
docker compose up -d

# Full stack (Redis + API + Web)
docker compose --profile full up --build -d
```

### Individual Containers

```bash
# API
docker build -t shopwave-api -f backend/Dockerfile ./backend
docker run -p 8000:8000 --env-file backend/.env shopwave-api

# Web
docker build -t shopwave-web -f frontend/Dockerfile ./frontend
```

### Railway / Render

Create two services from the same repo:

| Service | Root Directory | Start Command |
|---------|---------------|---------------|
| API | `backend` | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Web | `frontend` | Per platform docs |

Set `NEXT_PUBLIC_API_URL` on the web service to the API's public URL.

**Detailed split-host deployment** (e.g., Railway API + Render frontend):

1. **Railway**: Add Redis template + GitHub repo with root `backend`
2. **Railway**: Set env vars (`GROQ_API_KEY`, `DATABASE_URL`, `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CORS_ORIGINS`)
3. **Railway**: Generate domain, copy public API URL
4. **Render**: New Web Service, root `frontend`, set `NEXT_PUBLIC_API_URL` to Railway URL
5. Copy Render frontend URL back to Railway `CORS_ORIGINS`, redeploy

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| API | FastAPI + Uvicorn |
| Orchestration | LangGraph + LangChain |
| LLM Providers | Groq (free), OpenAI, Anthropic, Google, Ollama |
| Background Workers | Celery + Redis broker |
| Cache | Redis (aioredis) with multi-tier TTL |
| Database | Supabase Postgres (asyncpg pool) |
| Validation | Pydantic v2 (input + tool output + LLM output) |
| Auth | API Key + SlowAPI rate limiting |
| Frontend | Next.js 16 + React 19 + Tailwind 4 + Framer Motion |
| Testing | pytest + pytest-asyncio (51 tests) |
| Containers | Docker + Docker Compose |

---

## Project Structure

```
ksolves/
|-- backend/
|   |-- app/
|   |   |-- api/routes/        # FastAPI route handlers
|   |   |-- core/              # Config, LLM, cache, security, rate limiting
|   |   |-- db/                # Postgres layer + seed data
|   |   |-- graph/             # LangGraph: nodes, state, calibration
|   |   |-- models/            # Pydantic schemas (input, output, audit)
|   |   |-- services/          # Processor, audit, cost tracker, validator
|   |   |-- tasks/             # Celery task definitions
|   |   |-- tools/             # LangChain tools + validation + transparency
|   |   +-- main.py            # FastAPI app factory
|   |-- tests/                 # 51 tests
|   |-- scripts/               # Maintenance scripts
|   |-- Dockerfile
|   |-- requirements.txt
|   +-- .env.example
|-- frontend/
|   |-- app/                   # Next.js App Router pages
|   |-- components/            # UI (glass panels, neon buttons, timelines)
|   |-- lib/                   # API client, types, polling
|   |-- Dockerfile
|   +-- package.json
|-- sample_data/               # Reference data files
|-- docker-compose.yml         # Redis + optional full stack
|-- ARCHITECTURE.md            # Full architecture deep-dive
+-- README.md                  # This file
```

---

## Testing

```bash
cd backend && PYTHONPATH=. pytest tests/ -v --tb=short
```

Covers API routes, validation, smart routing, store, cost tracking, and security (51 tests).
