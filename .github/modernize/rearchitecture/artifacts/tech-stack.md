# Technology Stack

## Languages and Runtimes
- Python application runtime; version is not pinned in repository files.
- JavaScript frontend using ES modules; Node version is not declared in `frontend/package.json`.
- Docker Compose orchestrates local services.

## Backend
- Django 5.0.6 and Django REST Framework 3.15.1.
- SimpleJWT 5.3.1, django-cors-headers 4.3.1, django-filter 24.2, django-fsm 2.8.2.
- Celery 5.4.0 with django-celery-beat 2.6.0 and Flower 2.0.1.
- Channels 4.1.0, channels-redis 4.2.0 and Daphne 4.1.2.
- PostgreSQL via psycopg2-binary 2.9.9; pgvector 0.2.5.
- Redis 5.0.4 and django-redis 5.4.0.
- OpenAI SDK 1.30.1, pytesseract 0.3.10, pdf2image 1.17.0, pypdf 4.2.0, Pillow 10.3.0, requests 2.32.2.
- Gunicorn 22.0.0 and python-dotenv 1.0.1.

## Frontend
- React and React DOM 18.3.1.
- Vite 5.3.1 with `@vitejs/plugin-react` 4.3.1.
- React Router 6.24.0, TanStack React Query 5.45.1, Axios 1.7.2, Recharts 2.12.7, lucide-react 0.395.0, clsx 2.1.1.
- Tailwind CSS 3.4.4, PostCSS 8.4.38, Autoprefixer 10.4.19.

## Runtime Configuration
Django settings configure PostgreSQL, Redis, Celery queues, JWT, SMTP/Mailpit, LLM endpoint, Tesseract, CORS and outbound integrations. Vite proxies `/api` and `/ws` in development; nginx routes those paths in production.

## External Services
PostgreSQL with pgvector, Redis, SMTP, Tesseract, Frankfurter FX API, OpenAI-compatible LLM endpoint, Teams/generic webhooks.

## Observed Version Constraints
The repository pins package versions but does not declare Python or Node engine constraints. No deprecation or end-of-life determination is made here beyond recording the declared versions.
