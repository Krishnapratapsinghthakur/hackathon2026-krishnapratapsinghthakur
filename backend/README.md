# ShopWave API (FastAPI)

Run from this directory so `app` resolves and `.env` is picked up.

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then edit keys + DATABASE_URL
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Tests:

```bash
PYTHONPATH=. python -m pytest tests/ -v
```

Docker (from repository root):

```bash
docker compose --profile full up --build -d api
```

Celery worker (needs Redis):

```bash
PYTHONPATH=. celery -A app.core.celery_app:celery_app worker -l INFO -Q tickets,batch
```
