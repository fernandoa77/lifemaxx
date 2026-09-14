from pathlib import Path
import os

import dj_database_url
from decouple import Csv, config


BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config("SECRET_KEY", default="django-insecure-lifemax-change-me")
DEBUG = config("DEBUG", default=True, cast=bool)
ENVIRONMENT = config("ENVIRONMENT", default="development").lower()
IS_PRODUCTION = ENVIRONMENT == "production" or not DEBUG
ALLOWED_HOSTS = config("ALLOWED_HOSTS", default="localhost,127.0.0.1", cast=Csv())
CSRF_TRUSTED_ORIGINS = config("CSRF_TRUSTED_ORIGINS", default="", cast=Csv())
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = config("SECURE_SSL_REDIRECT", default=IS_PRODUCTION, cast=bool)
SESSION_COOKIE_SECURE = config("SESSION_COOKIE_SECURE", default=IS_PRODUCTION, cast=bool)
CSRF_COOKIE_SECURE = config("CSRF_COOKIE_SECURE", default=IS_PRODUCTION, cast=bool)
SECURE_HSTS_SECONDS = config("SECURE_HSTS_SECONDS", default=31536000 if IS_PRODUCTION else 0, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = IS_PRODUCTION
SECURE_HSTS_PRELOAD = IS_PRODUCTION

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "lifemax.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "dashboard.context_processors.global_context",
            ],
        },
    }
]
WSGI_APPLICATION = "lifemax.wsgi.application"
ASGI_APPLICATION = "lifemax.asgi.application"

_sqlite_url = f"sqlite:///{(BASE_DIR / 'db.sqlite3').as_posix()}"
_database_url = config("DATABASE_URL", default=_sqlite_url) or _sqlite_url
DATABASES = {
    "default": dj_database_url.config(default=_database_url, conn_max_age=600)
}

AUTH_PASSWORD_VALIDATORS = []  # MVP personal, sin autenticacion expuesta.
LANGUAGE_CODE = "es-mx"
TIME_ZONE = "America/Mexico_City"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"
SERVE_MEDIA_FILES = config("SERVE_MEDIA", default=not IS_PRODUCTION, cast=bool)
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# OpenRouter: una configuracion comun para todos los modulos de IA.
OPENROUTER_API_KEY = config("OPENROUTER_API_KEY", default="")
OPENROUTER_BASE_URL = config("OPENROUTER_BASE_URL", default="https://openrouter.ai/api/v1")
OPENROUTER_MODEL = config("OPENROUTER_MODEL", default="")
OPENROUTER_FALLBACK_MODELS = config("OPENROUTER_FALLBACK_MODELS", default="", cast=Csv())
OPENROUTER_HTTP_REFERER = config("OPENROUTER_HTTP_REFERER", default="")
OPENROUTER_APP_TITLE = config("OPENROUTER_APP_TITLE", default="LifeMax")
OPENROUTER_TIMEOUT = config("OPENROUTER_TIMEOUT", default=90, cast=int)
OPENROUTER_RETRIES = config("OPENROUTER_RETRIES", default=2, cast=int)
