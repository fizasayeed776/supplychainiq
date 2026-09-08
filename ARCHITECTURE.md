# SupplyChainIQ — Architecture Overview

## Service topology

```
Browser
  │
  ▼
nginx :80
  ├── /api/*        → web:8000  (gunicorn, WSGI, 3 workers)
  ├── /admin/*      → web:8000
  ├── /webhooks/*   → web:8000
  ├── /ws/*         → asgi:8001 (daphne, ASGI, WebSocket)
  └── /*            → frontend:80 (nginx serving Vite SPA)

web / asgi both depend on:
  ├── db:5432       (pgvector/postgres:16 — named volume pgdata)
  └── redis:6379    (redis:7-alpine — named volume redisdata)

Celery workers (all read from redis broker DB 0):
  ├── worker-ocr           queue: ocr         (2 concurrent)
  ├── worker-extraction    queue: extraction  (2 concurrent)
  ├── worker-matching      queue: matching    (2 concurrent)
  ├── worker-llm           queue: llm         (2 concurrent)
  └── worker-default       queue: default     (2 concurrent)

beat → redis (DB 0)   Celery Beat — nightly rematch schedule
flower :5555          Task monitor, reads from redis
mailpit :9025/:1025   Dev SMTP server
```

## WSGI / ASGI split

Django is served by two separate processes:

- **web (gunicorn/WSGI)** handles all synchronous HTTP: REST API, Django
  admin, inbound partner webhooks. Gunicorn runs 3 sync workers — no event
  loop, no coroutines required for straightforward request/response.

- **asgi (daphne/ASGI)** handles all WebSocket connections: the Dashboard
  pipeline feed, the Chat streaming interface, and Approval Room presence.
  Daphne runs the full ASGI `ProtocolTypeRouter`; HTTP requests that land
  here (e.g. the `/api/health/` healthcheck) are forwarded to Django's ASGI
  HTTP handler so the container healthcheck passes.

The nginx upstream blocks ensure a clean separation — no WebSocket traffic
ever reaches gunicorn, and no REST API traffic ever reaches daphne.

## Redis role separation

Redis runs as a single container but uses three isolated logical databases:

| DB | Role | Used by |
|---|---|---|
| 0 | Celery broker + result backend | All Celery workers, Beat |
| 1 | Django cache + webhook dedup store | web, asgi |
| 2 | Django Channels channel layer | asgi (WebSocket group messaging) |

The separation means a cache flush (DB 1) never affects in-flight task
messages (DB 0) or open WebSocket groups (DB 2).

## Celery queue design

Five dedicated queues allow independent worker scaling:

| Queue | Tasks | Concurrency |
|---|---|---|
| `ocr` | Tesseract OCR on scanned PDFs | 2 — I/O bound |
| `extraction` | LLM field extraction + vector embedding | 2 — LLM-rate-limited |
| `matching` | Three-way match agent chain | 2 — DB + LLM |
| `llm` | Vendor risk scoring, dispute drafting | 2 — LLM-rate-limited |
| `default` | Ingest routing, workflow, notifications | 2 — fast, low latency |

All tasks use `acks_late=True` and `prefetch_multiplier=1` — a task is
only acknowledged after successful completion, preventing data loss on
worker crash.

## Document pipeline — message flow

```
POST /api/documents/documents/   (multipart upload)
  │
  ▼ web (WSGI)
  1. SHA-256 hash → check UniqueConstraint(workspace, content_hash)
  2. Return 409 if duplicate; otherwise save Document row
  3. ingest_document.delay(doc_id)                         → queue: default
          │
          ▼ worker-default
  4. Detect if text-native PDF or scanned image
     ├── text-native → skip OCR, set ocr_status=not_needed
     └── scanned     → ocr_document.delay(doc_id)          → queue: ocr
                              │
                              ▼ worker-ocr
                       5. Tesseract → raw_text, confidence
                          → extract_document.delay(doc_id)  → queue: extraction
  6. extract_document (worker-extraction)
     └── run_extractor(doc) → LLM → structured JSON fields
         └── _materialize_structured_record(doc)
             ├── create Invoice / PurchaseOrder / DeliveryReceipt row
             ├── create LineItem rows
             └── embed_chunks.delay(doc_id)                → queue: extraction
  7. embed_chunks (worker-extraction)
     └── chunk raw_text → get_embeddings() → store Chunk rows (pgvector)
  8. try_three_way_match.delay(invoice_id)                 → queue: matching
          │
          ▼ worker-matching
  9. Matcher → find matching PO (exact po_number lookup, then semantic fallback)
 10. Comparator → align line items, emit discrepancy candidates
 11. Judge → filter false positives (rounding, unit conversion, partial delivery)
 12. update_or_create MatchResult
 13. channel_layer.group_send("dashboard_{workspace_id}", pipeline_progress)
          │
          ▼ Redis channel layer (DB 2)
 14. asgi / DashboardConsumer → push JSON to all connected WebSocket clients
          │
          ▼ Browser (Dashboard.jsx)
 15. useWebSocket onMessage → setFeed() → live pipeline feed row appears
```

## Chat streaming — message flow

```
Browser (Chat.jsx)
  │
  1. POST /api/chat/sessions/   → web (WSGI) → create ChatSession
  2. WS connect to /ws/chat/{session_id}/?token=<jwt>
          │
          ▼ nginx → asgi (daphne) → ChatConsumer.connect()
  3. JWTAuthMiddleware validates token → scope["user"]
  4. send({ question: "..." })
          │
          ▼ ChatConsumer.receive_json()
  5. hybrid_retrieve(): vector search (pgvector cosine) + full-text search → RRF merge
  6. maybe_run_aggregate_tool(): LLM decides if SQL-style aggregate is needed
  7. answer_question(): LLM generates answer with [chunk:N] citations
  8. Word-by-word token emission:
     for word in answer.split():
         send_json({"type": "token", "content": word + " "})
     send_json({"type": "done", "citations": [...]})
          │
          ▼ Browser
  9. "token" messages → streamingBufferRef accumulates → live typing effect
 10. "done" message → final message appended, citations rendered as pills
```

## Authentication

- **REST API**: JWT (`Authorization: Bearer <token>`). Access tokens expire
  in 30 min, refresh tokens in 7 days. Rotation + blacklist enabled.
- **WebSocket**: JWT passed as `?token=<access_token>` query parameter.
  `JWTAuthMiddleware` validates it on `connect()` and attaches `scope["user"]`.
  Anonymous connections are closed with code 4403.

## Data model summary

```
Workspace ──< WorkspaceMembership >── User
Workspace ──< Vendor ──< Contract
Workspace ──< Document (+ ScanRun)
  Document ──< LineItem
  Document ──1 PurchaseOrder
  Document ──1 Invoice
  Document ──1 DeliveryReceipt
  Document ──< Chunk (text + pgvector embedding)
Invoice ──1 MatchResult
  MatchResult.discrepancies: JSON[]  [{type, sku, expected, actual, reasoning}]
Invoice ──1 ApprovalFlow ──< ApprovalStep
MatchResult ──1 Dispute
Workspace ──< TriageRule
Workspace ──< ChatSession ──< ChatMessage
```

## Agent prompt iteration history

Every agent's system prompt has gone through multiple documented iterations
driven by evaluation results and production observations. The full log —
including problem observed, root cause, exact change made, and before/after
precision/recall — is in:

**[docs/PROMPT_ITERATION_LOG.md](docs/PROMPT_ITERATION_LOG.md)**

Entries cover all six agents: Extractor, Matcher, Comparator, Judge, Risk
Analyst, and Dispute Drafter. Each entry cross-references the
`eval_results/` JSON file produced by
`python backend/scripts/evaluate_matching.py` where applicable.

---

## Key design decisions

**No ORM calls inside Celery beat tasks** — Beat only enqueues; all DB work
happens inside the worker so crashes are retried cleanly.

**Deduplication via Redis `cache.add()`** — Webhook delivery IDs are stored
in Redis DB 1 with a 24-hour TTL. `cache.add()` is atomic: returns `True`
only if the key didn't already exist, so even under a 50-request storm only
one task is enqueued.

**Decimal-first money arithmetic** — All financial fields (`unit_price`,
`quantity`, `total_amount`, `max_amount`) use `DecimalField`. Comparisons
in the Comparator use `Decimal` arithmetic. The only `float()` casts are at
JSON serialization boundaries (the discrepancy payload `expected`/`actual`
fields) — never in the calculation path.

**LLM provider abstraction** — All LLM calls go through `apps/agents/client.py`
which reads `LLM_PROVIDER`, `LLM_BASE_URL`, and `LLM_API_KEY` from settings.
Switching from Groq to Ollama to OpenAI requires only `.env` changes.

**Migration discipline** — Every model change has a corresponding migration.
`makemigrations --check --dry-run` is clean (exit 0) as of Step 7.
