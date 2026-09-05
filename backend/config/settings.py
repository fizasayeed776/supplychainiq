"""
SupplyChainIQ settings.
12-factor: everything environment-specific comes from env vars, never hardcoded.
"""
import os
from datetime import timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-secret-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = os.environ.get("DJANGO_ALLOWED_HOSTS", "*").split(",")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    # 3rd party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "channels",
    "django_celery_beat",
    "django_fsm",
    "corsheaders",
    "pgvector.django",
    # local apps
    "apps.core",
    "apps.documents",
    "apps.matching",
    "apps.workflow",
    "apps.chat",
    "apps.realtime",
    "apps.webhooks",
    "apps.notifications",
    "apps.agents",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---- Database: Postgres + pgvector ----
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "supplychainiq"),
        "USER": os.environ.get("POSTGRES_USER", "supplychainiq"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "supplychainiq"),
        "HOST": os.environ.get("POSTGRES_HOST", "db"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---- CORS ----
CORS_ALLOWED_ORIGINS = os.environ.get(
    "CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://localhost"
).split(",")

# ---- DRF / JWT ----
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

# ---- Redis: three isolated logical DBs (broker / cache / channel layer) ----
REDIS_HOST = os.environ.get("REDIS_HOST", "redis")
REDIS_PORT = os.environ.get("REDIS_PORT", "6379")
REDIS_BROKER_DB = os.environ.get("REDIS_BROKER_DB", "0")
REDIS_CACHE_DB = os.environ.get("REDIS_CACHE_DB", "1")
REDIS_CHANNELS_DB = os.environ.get("REDIS_CHANNELS_DB", "2")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_CACHE_DB}",
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_CHANNELS_DB}"],
        },
    }
}

# ---- Celery: dedicated queues per pipeline stage ----
CELERY_BROKER_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_BROKER_DB}"
CELERY_RESULT_BACKEND = f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_BROKER_DB}"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TASK_ACKS_LATE = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_DEFAULT_QUEUE = "default"
CELERY_TASK_ROUTES = {
    "apps.documents.tasks.ingest_document": {"queue": "default"},
    "apps.documents.tasks.ocr_document": {"queue": "ocr"},
    "apps.documents.tasks.extract_document": {"queue": "extraction"},
    "apps.documents.tasks.embed_chunks": {"queue": "extraction"},
    "apps.matching.tasks.*": {"queue": "matching"},
    "apps.agents.tasks.*": {"queue": "llm"},
    "apps.workflow.tasks.*": {"queue": "default"},
    "apps.notifications.tasks.*": {"queue": "default"},
}
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_TASK_ANNOTATIONS = {
    "*": {"rate_limit": None},
}

# ---- LLM provider: thin, swappable abstraction (config-driven, never hardcoded) ----
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "openai")  # openai | ollama | groq | gemini
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "")  # override for ollama/groq/local endpoints
LLM_MODEL_FAST = os.environ.get("LLM_MODEL_FAST", "gpt-4o-mini")
LLM_MODEL_JUDGE = os.environ.get("LLM_MODEL_JUDGE", "gpt-4o")
EMBEDDING_API_KEY = os.environ.get("EMBEDDING_API_KEY", "")
EMBEDDING_PROVIDER = os.environ.get("EMBEDDING_PROVIDER", "gemini")
EMBEDDING_BASE_URL = os.environ.get("EMBEDDING_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "gemini-embedding-001")
EMBEDDING_DIM = int(os.environ.get("EMBEDDING_DIM", "1536"))
LLM_MONTHLY_USAGE_CAP_USD = float(os.environ.get("LLM_MONTHLY_USAGE_CAP_USD", "20"))

# ---- Free third-party services ----
FX_RATES_BASE_URL = os.environ.get("FX_RATES_BASE_URL", "https://api.frankfurter.app")
TEAMS_WEBHOOK_URL = os.environ.get("TEAMS_WEBHOOK_URL", "")

# ---- Email (Mailpit in dev) ----
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = os.environ.get("EMAIL_HOST", "mailpit")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "1025"))
EMAIL_USE_TLS = False
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@supplychainiq.local")
MAILPIT_API_URL = os.environ.get("MAILPIT_API_URL", "http://mailpit:8025")
MAILPIT_WORKSPACE_SLUG = os.environ.get("MAILPIT_WORKSPACE_SLUG", "demo")

# ---- Webhooks ----
PARTNER_WEBHOOK_SECRET = os.environ.get("PARTNER_WEBHOOK_SECRET", "dev-webhook-secret")

# ---- OCR ----
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "/usr/bin/tesseract")
OCR_LOW_CONFIDENCE_THRESHOLD = float(os.environ.get("OCR_LOW_CONFIDENCE_THRESHOLD", "0.65"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": os.environ.get("LOG_LEVEL", "INFO")},
}
