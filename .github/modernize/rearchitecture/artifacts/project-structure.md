# Project Structure

## Classification
Fullstack monorepo-style application with a Docker Compose deployment topology. The backend is a Django/DRF API and asynchronous processing system; the frontend is a Vite React single-page application.

## Top-Level Modules
- `backend/`: Django project, domain apps, Celery tasks, Channels consumers, templates and media.
- `frontend/`: React pages/components/hooks, API client, Vite and Tailwind configuration.
- `nginx/`: production reverse proxy for SPA, API, WebSocket and media traffic.
- `docker-compose.yml`: local runtime topology for database, Redis, web, ASGI, workers, Beat, Flower, frontend, mail and nginx.

## Backend Layers
- Entry/configuration: `backend/config/{settings,urls,wsgi,asgi,celery}.py`.
- HTTP/controller: each app's `views.py`, `urls.py`, `serializers.py`.
- Domain/persistence: each app's `models.py`.
- Application workflows: `documents/tasks.py`, `matching/tasks.py`, `workflow/tasks.py`, `agents/tasks.py`.
- Integration/adapters: `agents/client.py`, `documents/ocr.py`, `workflow/outbound.py`, `notifications/teams.py`, `chat/rag.py`.
- Realtime: `realtime/{middleware,routing,consumers}.py`.

## Frontend Layers
- Bootstrap and routing: `src/main.jsx`, `src/App.jsx`.
- Pages: Dashboard, Documents, Matches, Approvals, Vendors, Chat and Settings.
- Shared UI: `src/components/`.
- Transport/state hooks: `src/lib/api.js`, `src/hooks/useWebSocket.js`.

## Functional Areas
Tenancy and core administration; document ingestion and OCR; structured procurement records; three-way invoice matching; approvals and disputes; vendor risk; RAG chat; realtime collaboration; partner webhooks; notifications and compliance reporting.

## Entry Points
Django root URL dispatch, WSGI, ASGI, Celery autodiscovery/Beat, partner webhook, Channels routes, and React BrowserRouter routes. See `unit_graph.yaml` for the externally triggerable unit index.
