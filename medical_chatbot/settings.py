"""
Django settings for medical_chatbot -- Render + Vercel production config.
"""

import os
from pathlib import Path

import dj_database_url
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# -- Core --------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable is not set")

DEBUG = os.getenv("DEBUG", "False") == "True"

ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")
    if h.strip()
]

# -- Apps --------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "corsheaders",
    "chatbot",
]

# -- Middleware ---------------------------------------------------------------
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

ROOT_URLCONF = "medical_chatbot.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
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

WSGI_APPLICATION = "medical_chatbot.wsgi.application"

# -- Database ----------------------------------------------------------------
# KEY FIX: CONN_HEALTH_CHECKS=True makes Django ping the connection before
# reusing it from the pool.  On Render free-tier the PostgreSQL server silently
# drops idle connections after ~5 minutes.  With CONN_MAX_AGE=600 the dead
# socket stays in Django's pool; the next query that tries to use it gets
# "server closed the connection unexpectedly" which escapes all the view-level
# try/except blocks and shows as 500.  CONN_HEALTH_CHECKS silently reconnects.
_database_url = os.getenv("DATABASE_URL")
if _database_url:
    DATABASES = {
        "default": dj_database_url.config(
            default=_database_url,
            conn_max_age=60,
            conn_health_checks=True,
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE":             "django.db.backends.postgresql",
            "NAME":               os.getenv("DB_NAME", "medical_chatbot"),
            "USER":               os.getenv("DB_USER", "postgres"),
            "PASSWORD":           os.getenv("DB_PASSWORD", ""),
            "HOST":               os.getenv("DB_HOST", "localhost"),
            "PORT":               os.getenv("DB_PORT", "5432"),
            "CONN_MAX_AGE":       60,
            "CONN_HEALTH_CHECKS": True,
        }
    }

# -- Cache -------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND":  "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "dawa-cache",
        "TIMEOUT":  3600,
        "OPTIONS":  {"MAX_ENTRIES": 2000},
    }
}

# -- CORS --------------------------------------------------------------------
_cors_raw = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://localhost:5500,http://127.0.0.1:5500",
)
CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]
CORS_ALLOWED_ORIGIN_REGEXES = [r"^https://.*\.vercel\.app$"]
CORS_ALLOW_CREDENTIALS = False
CORS_ALLOW_METHODS     = ["DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"]
CORS_ALLOW_HEADERS     = [
    "accept", "accept-encoding", "authorization", "content-type",
    "dnt", "origin", "user-agent", "x-csrftoken", "x-requested-with",
]

# -- Static files ------------------------------------------------------------
STATIC_URL  = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

_custom_static = BASE_DIR / "static"
STATICFILES_DIRS = (
    [_custom_static]
    if _custom_static.is_dir() and _custom_static != STATIC_ROOT
    else []
)

STORAGES = {
    "default":     {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# -- Auth password validators ------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# -- i18n --------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE     = "Africa/Nairobi"
USE_I18N      = True
USE_TZ        = True

# -- Security (production only) ----------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT            = False
    SECURE_PROXY_SSL_HEADER        = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE          = True
    CSRF_COOKIE_SECURE             = True
    SECURE_HSTS_SECONDS            = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF    = True

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -- Logging -----------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{levelname}] {asctime} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": "INFO"},
    "loggers": {
        "chatbot": {
            "handlers":  ["console"],
            "level":     "DEBUG" if DEBUG else "INFO",
            "propagate": False,
        },
        "django.request": {
            "handlers":  ["console"],
            "level":     "WARNING",
            "propagate": False,
        },
    },
}
