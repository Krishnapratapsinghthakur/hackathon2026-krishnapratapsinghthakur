# ShopWave Autonomous Support Resolution Agent

AI-powered customer support agent that ingests, classifies, and autonomously resolves support tickets using **LangGraph** orchestration with **LangChain** tools, persisted to **Supabase Postgres**.

## Monorepo layout

| Path | Role | Default port |
|------|------|----------------|
| **`backend/`** | FastAPI, LangGraph, Celery tasks, pytest, `Dockerfile`, `.env` | **8000** |
| **`frontend/`** | Next.js UI (`NEXT_PUBLIC_API_URL` → API) | **3000** |
| **`docker-compose.yml`** (repo root) | Shared **Redis**; optional **`--profile full`** builds API + Web | Redis **6379** |

The two apps are **separate packages** (Python vs Node), different ports, and independent deploy roots — no file or dependency collision.

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                           │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌───────────────────┐   │
│  │  /health  │  │ /tickets │  │  /audit  │  │    /settings      │   │
│  └──────────┘  └────┬─────┘  └──────────┘  └───────────────────┘   │
│                     │                                                │
│        ┌────────────┴────────────┐                                   │
│        │  Security Middleware     │                                   │
│        │  • API Key Auth          │                                   │
│        │  • Rate Limiting (60/m)  │                                   │
│        │  • Request ID Tracking   │                                   │
│        │  • CORS Policy           │                                   │
│        └────────────┬────────────┘                                   │
│                     │                                                │
│   ┌─────────────────┴──────────────────┐                             │
│   │        Ticket Processor            │                             │
│   │  • Pydantic validation             │                             │
│   │  • Duplicate detection             │                             │
│   │  • Customer/order pre-fetch        │                             │
│   │  • Smart model routing             │                             │
│   │  • Retry + backoff + DLQ           │                             │
│   └─────────────────┬──────────────────┘                             │
│                     │                                                │
│   ┌─────────────────┴──────────────────┐                             │
│   │      LangGraph State Machine       │                             │
│   │  classify → agent ↔ tools → parse  │                             │
│   │  ReAct loop with conditional edges │                             │
│   └─────────────────┬──────────────────┘                             │
│                     │                                                │
│   ┌─────────────────┴──────────────────┐                             │
│   │    LLM Factory (Multi-Provider)    │                             │
│   │  Groq (free) │ OpenAI │ Anthropic  │                             │
│   └────────────────────────────────────┘                             │
│                     │                                                │
│   ┌─────────────────┴──────────────────┐                             │
│   │        Supabase Postgres           │                             │
│   │  8 tables • asyncpg pool           │                             │
│   │  Domain + Operational data         │                             │
│   └────────────────────────────────────┘                             │
└──────────────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|---|---|
| API Framework | FastAPI + Uvicorn |
| LLM Orchestration | LangGraph + LangChain |
| LLM Providers | Groq (free), OpenAI, Anthropic |
| Database | Supabase Postgres (asyncpg) |
| Validation | Pydantic v2 |
| Auth | API Key (X-API-Key header) |
| Rate Limiting | SlowAPI |
| Testing | pytest + pytest-asyncio |
| Deployment | Docker Compose (root), Railway/Render (set **Root Directory** per service) |

## Quick Start

```bash
git clone <repo-url> && cd ksolves

# ── Backend (FastAPI) ─────────────────────────────────────────
cd backend
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env: GROQ_API_KEY, DATABASE_URL, CORS_ORIGINS (include http://localhost:3000)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ── Frontend (Next.js) — second terminal ─────────────────────
cd ../frontend
cp env.sample .env.local
# .env.local: NEXT_PUBLIC_API_URL=http://localhost:8000
npm install && npm run dev
# Open http://localhost:3000

# ── Tests (from backend/) ────────────────────────────────────
cd ../backend && PYTHONPATH=. pytest tests/ -v
```

### Local Redis + API + worker (optional)

From repo root (starts Redis via Docker if available, then API from `backend/`):

```bash
bash backend/scripts/run-all.sh
```

## Environment Configuration

```bash
# Development (Groq free tier — $0.00)
ENVIRONMENT=development
GROQ_API_KEY=gsk_your-key

# Production (OpenAI paid models)
ENVIRONMENT=production
OPENAI_API_KEY=sk-your-key
```

Just flip `ENVIRONMENT` — provider, models, and routing presets switch automatically.

## API Endpoints

| Method | Endpoint | Description | Rate Limit |
|---|---|---|---|
| GET | `/health` | Status, DB mode, LLM config | — |
| POST | `/tickets/process` | Process single ticket | 30/min |
| POST | `/tickets/batch` | Process batch of tickets | 5/min |
| GET | `/tickets/sample` | List 20 sample tickets | — |
| GET | `/audit` | All audit entries | — |
| GET | `/audit/{ticket_id}` | Single ticket audit trail | — |
| GET | `/audit/dlq` | Dead-letter queue | — |
| GET | `/settings` | Current LLM config | — |
| GET | `/settings/models` | Supported models + pricing | — |
| GET | `/settings/costs` | Token usage + cost breakdown | — |
| GET | `/docs` | Swagger UI | — |

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

## Security

- **API Key Auth** — Set `API_KEY` in `.env` to require `X-API-Key` header (disabled when empty)
- **Rate Limiting** — 30 req/min for single tickets, 5 req/min for batch
- **CORS** — Configurable origins via `CORS_ORIGINS` (comma-separated)
- **Request ID** — Every response includes `X-Request-ID` for tracing
- **Input Validation** — Pydantic validators on all inputs (email format, non-empty body, etc.)
- **No hardcoded secrets** — All sensitive config via environment variables

## Smart Model Routing

Heuristic engine that decides fast (cheap) vs power (expensive) model per ticket:

| Signal | Route |
|---|---|
| VIP/Premium customer | → Power model |
| Threatening/legal language | → Power model |
| Fraud/social engineering patterns | → Power model |
| High-value order (>$200) | → Power model |
| Vague ticket (<10 words, no IDs) | → Power model |
| Multiple orders (>2) | → Power model |
| Standard ticket | → Fast model |

## Project Structure

Python package lives under **`backend/`** (run commands from that directory).

```
backend/
├── app/                        # FastAPI + LangGraph + services
├── tests/
├── requirements.txt
├── Dockerfile
├── Procfile
└── .env.example

frontend/
├── app/                        # Next.js App Router
├── components/
├── lib/
├── package.json
├── Dockerfile
└── env.sample
```

## Deployment

**Ports:** API **8000**, UI **3000**, Redis **6379** — do not bind two services to the same host port.

```bash
# API image only (build context = backend/)
docker build -t shopwave-api -f backend/Dockerfile ./backend
docker run -p 8000:8000 --env-file backend/.env shopwave-api

# UI image (build context = frontend/)
docker build -t shopwave-web -f frontend/Dockerfile ./frontend

# Redis + API + Web together (stop local dev servers first to free ports)
docker compose --profile full up --build -d
```

**Railway / Render:** create **two services** from the same repo — set **Root Directory** to `backend` (start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`) and `frontend` (build/start per platform docs). Set `NEXT_PUBLIC_API_URL` on the frontend service to the **public URL** of the API.

### Frontend on Render + Backend on Railway (split hosts)

1. **Railway** — New project → add **Redis** (template) → **New** → **GitHub Repo** → pick this repo → set **Root Directory** to `backend` → deploy (uses `backend/Dockerfile`; listens on `PORT`).
2. **Railway** — In the **backend** service → **Variables**: `GROQ_API_KEY`, optional `DATABASE_URL`, `ENVIRONMENT`, and point `REDIS_URL` / `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` at your Redis (same host, paths `/0`, `/1`, `/2` if needed). Set `CORS_ORIGINS` to `*` until the UI URL exists, then set it to your **Render** frontend URL only.
3. **Railway** — **Settings → Networking → Generate Domain** (or add a custom domain). Copy the public API URL (e.g. `https://your-api.up.railway.app`).
4. **Render** — **New Web Service** → same GitHub repo → **Root Directory** `frontend` → **Node** → Build: `npm install && npm run build` → Start: `npm run start` → add **`NEXT_PUBLIC_API_URL`** = your Railway API URL (no trailing slash).
5. After Render is **Live**, copy the frontend URL → paste into Railway **`CORS_ORIGINS`** → redeploy backend.

## Testing

```bash
cd backend && PYTHONPATH=. pytest tests/ -v --tb=short
```

Covers API routes, validation, smart routing, store, cost tracking, and security (51 tests).
