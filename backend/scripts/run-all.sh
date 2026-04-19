#!/usr/bin/env bash
# Start Redis (repo-root docker compose), Celery worker, and FastAPI from the backend package.
set -euo pipefail
BACKEND_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$BACKEND_ROOT/.." && pwd)"
cd "$BACKEND_ROOT"

export PYTHONPATH="$BACKEND_ROOT"

REDIS_URL="${REDIS_URL:-}"
if [[ -z "$REDIS_URL" ]] && [[ -f "$BACKEND_ROOT/.env" ]]; then
  REDIS_URL="$(grep -E '^[[:space:]]*REDIS_URL=' "$BACKEND_ROOT/.env" | head -1 | cut -d= -f2- | tr -d '\r' | sed 's/^[\"'\'']//;s/[\"'\'']$//')" || true
fi
REDIS_URL="${REDIS_URL:-redis://localhost:6379/0}"

REDIS_UP=0
if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
  echo "==> Starting Redis (docker compose from repo root)..."
  (cd "$REPO_ROOT" && docker compose up -d redis)
  for _ in $(seq 1 40); do
    if (cd "$REPO_ROOT" && docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG); then
      REDIS_UP=1
      break
    fi
    sleep 0.25
  done
  [[ "$REDIS_UP" -eq 1 ]] && echo "==> Redis (Docker) is up."
fi

if [[ "$REDIS_UP" -eq 0 ]] && command -v redis-cli >/dev/null 2>&1; then
  if redis-cli -u "$REDIS_URL" ping 2>/dev/null | grep -q PONG; then
    echo "==> Host Redis responds on ${REDIS_URL}."
    REDIS_UP=1
  fi
fi

mkdir -p "$BACKEND_ROOT/.logs"
LOGDIR="$BACKEND_ROOT/.logs"

if [[ "$REDIS_UP" -eq 1 ]]; then
  echo "==> Starting Celery worker (queues: tickets, batch)..."
  cd "$BACKEND_ROOT"
  nohup python3 -m celery -A app.core.celery_app:celery_app worker -l INFO -Q tickets,batch \
    >>"$LOGDIR/celery.log" 2>&1 &
  echo $! >"$LOGDIR/celery.pid"
else
  echo ""
  echo "WARN: Redis is not reachable. Skipping Celery worker."
  echo "      From repo root:  cd $REPO_ROOT && docker compose up -d"
  echo ""
  rm -f "$LOGDIR/celery.pid"
fi

echo "==> Starting Uvicorn on :8000 (PYTHONPATH=$BACKEND_ROOT)..."
cd "$BACKEND_ROOT"
nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 \
  >>"$LOGDIR/uvicorn.log" 2>&1 &
echo $! >"$LOGDIR/uvicorn.pid"

sleep 3
echo ""
if [[ -f "$LOGDIR/celery.pid" ]]; then
  echo "PIDs:  Celery $(cat "$LOGDIR/celery.pid")   Uvicorn $(cat "$LOGDIR/uvicorn.pid")"
else
  echo "PIDs:  Uvicorn $(cat "$LOGDIR/uvicorn.pid")  (Celery not started — no Redis)"
fi
echo "Logs:  $LOGDIR/celery.log   $LOGDIR/uvicorn.log"
echo "API:   http://localhost:8000/health"
echo "UI:    http://localhost:3000 (run from $REPO_ROOT/frontend)"
echo ""
curl -sf http://127.0.0.1:8000/health | python3 -m json.tool || echo "Health check failed (wait a few seconds and retry)."
