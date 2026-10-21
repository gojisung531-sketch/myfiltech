"""Base settings shared by all environments. See specs/01-architecture.md §4."""

from datetime import timedelta
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from config.env import (
    env_bool,
    env_int,
    env_list,
    env_str,
    load_dotenv,
    parse_database_url,
)

APP_VERSION = "0.1.0"

BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
FONTS_DIR = BACKEND_DIR / "fonts"  # Noto Sans KR for PDF (specs/09 §5)

load_dotenv(BACKEND_DIR / ".env")

SECRET_KEY = env_str("DJANGO_SECRET_KEY")
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is not set (see .env.example)")

DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    # Local
    "apps.core",
    "apps.accounts",
    "apps.llm",
    "apps.documents",
    "apps.company",
    "apps.bids",
    "apps.evaluation",
    "apps.drafts",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# Database — local PostgreSQL 18 (specs/01 §4.1), no docker.
DATABASE_URL = env_str("DATABASE_URL")
if not DATABASE_URL:
    raise ImproperlyConfigured("DATABASE_URL is not set (see .env.example)")
DATABASES = {"default": parse_database_url(DATABASE_URL)}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = env_str("TIME_ZONE", "Asia/Seoul")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BACKEND_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env_str("MEDIA_ROOT", "./media"))
if not MEDIA_ROOT.is_absolute():
    MEDIA_ROOT = (BACKEND_DIR / MEDIA_ROOT).resolve()

INITIAL_DATA_DIR = Path(env_str("INITIAL_DATA_DIR", "../initial-data"))
if not INITIAL_DATA_DIR.is_absolute():
    INITIAL_DATA_DIR = (BACKEND_DIR / INITIAL_DATA_DIR).resolve()

MAX_UPLOAD_MB = env_int("MAX_UPLOAD_MB", 50)
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024

# Fernet key used by apps.llm.crypto to encrypt LLM API keys.
FIELD_ENCRYPTION_KEY = env_str("FIELD_ENCRYPTION_KEY", "")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# REST framework — specs/01 §6
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 20,
    "EXCEPTION_HANDLER": "apps.core.exceptions.api_exception_handler",
}

# JWT — specs/03 §1
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": True,
    "AUTH_HEADER_TYPES": ("Bearer",),
}

CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:5173")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"},
    },
    "filters": {
        "mask_secrets": {"()": "apps.core.logging.SecretMaskingFilter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["mask_secrets"],
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    # WeasyPrint logs every layout step at INFO; fontTools subsetting is just as chatty.
    "loggers": {
        "weasyprint": {"level": "WARNING"},
        "fontTools": {"level": "WARNING"},
    },
}
