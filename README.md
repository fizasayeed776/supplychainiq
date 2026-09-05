# SupplyChainIQ

AI-powered procurement & vendor intelligence platform. Django + Celery +
Channels backend, multi-agent matching engine, RAG chat, and a React
frontend — all Dockerized, free/open-source stack.

## Project layout

```
sciq/
├── backend/     Django project (WSGI + ASGI, Celery, Channels, agents)
├── frontend/    React (Vite) SPA
├── nginx/       Reverse proxy routing /api, /ws, and /
└── docker-compose.yml
```

## Services (14 containers)

| Service | Port (host) | Purpose |
|---|---|---|
| nginx | 80 | Reverse proxy: routes /api → web, /ws → asgi, / → frontend |
| web | — | Django WSGI (gunicorn, 3 workers) — REST API |
| asgi | — | Django ASGI (daphne) — WebSocket consumers (dashboard, chat, approvals) |
| frontend | — | React SPA (nginx, pre-built Vite bundle) |
| db | — | PostgreSQL 16 + pgvector |
| redis | — | Broker (DB 0) · Cache/dedup (DB 1) · Channels (DB 2) |
| worker-ocr | — | Celery worker: `ocr` queue (2 concurrency) |
| worker-extraction | — | Celery worker: `extraction` queue (2 concurrency) |
| worker-matching | — | Celery worker: `matching` queue (2 concurrency) |
| worker-llm | — | Celery worker: `llm` queue (2 concurrency) |
| worker-default | — | Celery worker: `default` queue (2 concurrency) |
| beat | — | Celery Beat — nightly rematch schedule |
| flower | 5555 | Celery task monitor |
| mailpit | 9025 | Dev email inbox (SMTP on :1025 inside the network) |

All services except nginx have Docker healthchecks. `web`, `asgi`, and all
five workers use `depends_on: {db: service_healthy, redis: service_healthy}`
so they never start before their dependencies are ready.

## Quickstart

1. Copy the env template and fill in your keys:
   ```bash
   cp backend/.env.example backend/.env
   # Set LLM_API_KEY (Groq) and EMBEDDING_API_KEY (Gemini) in backend/.env
   ```
2. Build and start everything:
   ```bash
   docker compose up --build
   ```
3. Run migrations and create a superuser (first time only):
   ```bash
   docker compose exec web python manage.py migrate
   docker compose exec web python manage.py createsuperuser
   ```
4. Seed the test corpus (optional — populates ~30 demo documents):
   ```bash
   docker compose exec web python scripts/build_test_corpus.py
   ```
5. Open:
   - App: http://localhost/
   - Django admin: http://localhost/admin/
   - Mailpit (dev email): http://localhost:9025
   - Flower (Celery monitor): http://localhost:5555

## Environment variables

All variables live in `backend/.env` (copy from `.env.example`).
Key variables:

| Variable | Purpose | Example |
|---|---|---|
| `DJANGO_SECRET_KEY` | Django secret | `change-me-in-production` |
| `LLM_PROVIDER` | LLM backend (`groq`, `openai`, `ollama`) | `groq` |
| `LLM_API_KEY` | API key for the LLM provider | `gsk_…` |
| `LLM_MODEL_FAST` | Fast model for extraction / chat | `llama-3.1-8b-instant` |
| `LLM_MODEL_JUDGE` | Judge model for match decisions | `llama-3.3-70b-versatile` |
| `EMBEDDING_PROVIDER` | Embedding backend (`gemini`) | `gemini` |
| `EMBEDDING_API_KEY` | API key for embeddings | `AIza…` |
| `EMBEDDING_MODEL` | Embedding model name | `gemini-embedding-001` |
| `EMBEDDING_DIM` | Embedding vector dimension | `1536` |
| `POSTGRES_*` | Database credentials | see .env.example |
| `REDIS_BROKER_DB` | Redis DB for Celery broker | `0` |
| `REDIS_CACHE_DB` | Redis DB for cache + dedup | `1` |
| `REDIS_CHANNELS_DB` | Redis DB for Channels layer | `2` |
| `PARTNER_WEBHOOK_SECRET` | HMAC secret for inbound webhooks | `dev-webhook-secret` |
| `LLM_MONTHLY_USAGE_CAP_USD` | Cost guard — soft cap | `20` |

## Local frontend dev (hot reload, outside Docker)

```bash
cd frontend
npm install
npm run dev   # http://localhost:5173 — proxies /api to :8000, /ws to :8001
```

## Swapping the LLM provider

Everything routes through `apps/agents/client.py`. To use a local model:

```
LLM_PROVIDER=ollama
LLM_BASE_URL=http://host.docker.internal:11434/v1
LLM_MODEL_FAST=llama3.1
LLM_API_KEY=ollama
```

No agent code changes needed.

## Testing

```bash
# Full test suite (31 tests across 5 apps)
docker compose exec web python manage.py test apps --keepdb

# Coverage report (currently 71%)
docker compose exec web coverage run manage.py test apps --keepdb
docker compose exec web coverage report --include="apps/*"
```

## Testing the webhook pipeline

```bash
docker compose exec web python scripts/partner_simulator.py normal
docker compose exec web python scripts/partner_simulator.py replay       # deduped → 200
docker compose exec web python scripts/partner_simulator.py storm --count 50  # 1 accepted, 49 deduped
```

Note: the simulator targets `http://127.0.0.1/webhooks/partner/` — run it
from the host machine (not inside the container) since that address resolves
to the nginx proxy on the host.

## Production

Set a monthly usage cap on your LLM provider's dashboard matching
`LLM_MONTHLY_USAGE_CAP_USD`. Change `DJANGO_DEBUG=false`,
`DJANGO_SECRET_KEY` to a long random value, and `POSTGRES_PASSWORD` to
something strong.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for a full description of the
service topology, message flow, and design decisions.
