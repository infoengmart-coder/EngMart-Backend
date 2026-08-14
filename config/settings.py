"""
Django settings for Eng-Mart backend.
Uses environment variables for all sensitive/environment-specific values.
"""
import os
from pathlib import Path
from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv
import dj_database_url

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Security
SECRET_KEY = os.environ.get('DJANGO_SECRET_KEY', 'dev-insecure-key-change-in-production')
# Defaults to False: a missing DEBUG variable on a production host must never
# expose tracebacks, settings and SQL. Local dev sets DEBUG=True in .env.
DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(',')

# ─── Production hardening ─────────────────────────────────────
# All of this is gated on DEBUG=False so local development over plain HTTP
# keeps working; a dev machine that forced HTTPS redirects would be unusable.
if not DEBUG:
    # The site is served over HTTPS, so cookies must never travel in clear text.
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = os.environ.get('SECURE_SSL_REDIRECT', 'True').lower() in ('true', '1', 'yes')

    # Most PaaS hosts (Railway, Render, Fly) terminate TLS at their proxy and
    # forward this header. Without it Django thinks every request is plain HTTP
    # and SECURE_SSL_REDIRECT causes an infinite redirect loop.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

    # HSTS: start at 1 hour. Raise to a year (31536000) only once HTTPS is
    # confirmed working — browsers cache this and it cannot be undone quickly.
    SECURE_HSTS_SECONDS = int(os.environ.get('SECURE_HSTS_SECONDS', '3600'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False

    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

    # Refuse to boot with the development secret key in production, rather than
    # silently running with a key that is in the repository.
    if SECRET_KEY.startswith('dev-insecure') or len(SECRET_KEY) < 50:
        raise ImproperlyConfigured(
            'DJANGO_SECRET_KEY is missing or too weak for production. '
            'Generate one with:  python -c "from django.core.management.utils '
            'import get_random_secret_key; print(get_random_secret_key())"'
        )

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    # Third party
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    # Local apps
    'apps.common',
    'apps.authentication',
    'apps.categories',
    'apps.brands',
    'apps.products',
    'apps.inquiries',
    'apps.orders',
    'apps.banners',
    'apps.site_settings',
    'apps.quotations',
    'apps.accounts',
    'apps.notifications',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# Database — PostgreSQL via Supabase (or any DATABASE_URL)
# The database lives in another region, so opening a fresh connection costs
# roughly a second in TCP + TLS + auth. CONN_MAX_AGE keeps it open between
# requests; conn_health_checks makes Django verify the socket is still alive
# and transparently reconnect, which is what makes this safe with a pooler.
DATABASES = {
    'default': dj_database_url.config(
        default=os.environ.get('DATABASE_URL', 'sqlite:///db.sqlite3'),
        conn_max_age=int(os.environ.get('DB_CONN_MAX_AGE', '600')),
        conn_health_checks=True,
    )
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Karachi'
USE_I18N = True
USE_TZ = True

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STORAGES = {
    'default': {
        'BACKEND': 'django.core.files.storage.FileSystemStorage',
    },
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage',
    },
}

# Media files (product images, brand logos)
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    # Honours ?page_size= (the frontend already sends it), capped so nobody can
    # ask for the whole 3,000-product catalog in one request.
    'DEFAULT_PAGINATION_CLASS': 'apps.common.pagination.StandardPagination',
    'PAGE_SIZE': 24,
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
        'rest_framework.renderers.BrowsableAPIRenderer',
    ],
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(days=1),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    # Without this, a rotated refresh token stays usable — defeating rotation.
    'BLACKLIST_AFTER_ROTATION': True,
    'AUTH_HEADER_TYPES': ('Bearer',),
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
}

# CORS — Allow Next.js frontend
CORS_ALLOWED_ORIGINS = os.environ.get(
    'CORS_ORIGINS', 'http://localhost:3000'
).split(',')
CORS_ALLOW_CREDENTIALS = True

# ─── "Continue with Google" via Clerk ─────────────────────────
# Clerk brokers the Google OAuth flow; Django + SimpleJWT stays the account
# system of record (see apps/authentication/clerk_views.py for why).
#
# Only these two keys normally need setting — both come from the same Clerk
# dashboard page. The publishable key must ALSO be set in the frontend as
# NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY, and the two must be from the same Clerk
# instance or tokens will fail the issuer check. Leave them blank and the
# endpoint returns 503 rather than half-working.
CLERK_PUBLISHABLE_KEY = os.environ.get('CLERK_PUBLISHABLE_KEY', '').strip()
CLERK_SECRET_KEY = os.environ.get('CLERK_SECRET_KEY', '').strip()

# Both are derived from the publishable key and only need setting if Clerk is
# on a custom domain and the derivation is not what you want.
CLERK_FRONTEND_API = os.environ.get('CLERK_FRONTEND_API', '').strip()
CLERK_JWKS_URL = os.environ.get('CLERK_JWKS_URL', '').strip()

# Comma-separated origins allowed to mint session tokens, e.g.
# "https://eng-mart.com,https://www.eng-mart.com". Checked against the token's
# `azp` claim, which is what prevents a token minted for another site being
# replayed here. Unset = not enforced, which is fine locally.
CLERK_ALLOWED_ORIGINS = os.environ.get('CLERK_ALLOWED_ORIGINS', '').strip()

# ─── Email (SendGrid via SMTP relay) ──────────────────────────
# Uses Django's built-in SMTP backend, so no extra dependency is required.
# When SENDGRID_API_KEY is unset the console backend is used instead, which
# prints emails to the terminal — handy in development and safe in CI.
SENDGRID_API_KEY = os.environ.get('SENDGRID_API_KEY', '').strip()
SENDGRID_FROM_EMAIL = os.environ.get('SENDGRID_FROM_EMAIL', '').strip()

# Where internal notifications (new order / new inquiry) are delivered.
SALES_NOTIFICATION_EMAIL = os.environ.get(
    'SALES_NOTIFICATION_EMAIL', SENDGRID_FROM_EMAIL,
).strip()

# Reply-To on customer-facing mail. The From address must be a domain we control
# (for SPF/DKIM alignment), but replies should land in the inbox the team
# actually works from — typically a mailbox on a different provider.
REPLY_TO_EMAIL = os.environ.get('REPLY_TO_EMAIL', SALES_NOTIFICATION_EMAIL).strip()

DEFAULT_FROM_EMAIL = SENDGRID_FROM_EMAIL or 'no-reply@eng-mart.com'
SERVER_EMAIL = DEFAULT_FROM_EMAIL

if SENDGRID_API_KEY:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.sendgrid.net'
    EMAIL_PORT = 587
    EMAIL_USE_TLS = True
    EMAIL_HOST_USER = 'apikey'  # literal string required by SendGrid's SMTP relay
    EMAIL_HOST_PASSWORD = SENDGRID_API_KEY
    EMAIL_TIMEOUT = 10  # never let a hung SMTP call stall a checkout request
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Public site URL used when building links inside emails.
FRONTEND_URL = os.environ.get('FRONTEND_URL', 'http://localhost:3000').rstrip('/')

# ─── Cache ────────────────────────────────────────────────────
# Cache for public catalog responses.
#
# Which backend wins depends on where the app server is running, because the
# two have opposite cost profiles:
#
#   LocMemCache  in-process, ~0ms a read, but private to each worker. Fine for
#                one dev process; wasteful and inconsistent across N workers.
#   Redis        shared by every worker, but each read is a network round trip.
#
# In production the app server and Redis sit in the same region, so a read is
# well under a millisecond and sharing wins outright. On a laptop in Karachi
# talking to Upstash Mumbai a read is ~50ms, and a page doing several cache
# lookups ends up SLOWER than the in-process cache it replaced. So Redis is
# used when DEBUG is off, and locally only if explicitly forced.
#
# Set USE_REDIS=1 in .env to exercise the real Redis path in local dev.
_redis_url = os.environ.get('REDIS_URL', '').strip()
_force_redis = os.environ.get('USE_REDIS', '').strip().lower() in ('1', 'true', 'yes')
if _redis_url and (not DEBUG or _force_redis):
    CACHES = {
        'default': {
            # Degrades to cache-miss instead of HTTP 500 when Redis is
            # unreachable or the plan's command quota is exhausted.
            'BACKEND': 'apps.common.redis_cache.ResilientRedisCache',
            'LOCATION': _redis_url,
            'OPTIONS': {
                # Without these a hung connection holds the worker until the
                # OS gives up, which turns a cache blip into an outage.
                'socket_connect_timeout': 3,
                'socket_timeout': 3,
                'retry_on_timeout': True,
                'health_check_interval': 30,
            },
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'engmart-catalog',
            'OPTIONS': {'MAX_ENTRIES': 2000},
        }
    }

# ─── Logging ──────────────────────────────────────────────────
# Email is sent on a background thread and never raises, so without this the
# only signal that delivery failed would be a customer saying they got nothing.
# Surface every send outcome on the console.
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'simple': {'format': '[{levelname}] {asctime} {name}: {message}', 'style': '{'},
    },
    'handlers': {
        'console': {'class': 'logging.StreamHandler', 'formatter': 'simple'},
    },
    'loggers': {
        'apps': {'handlers': ['console'], 'level': 'INFO', 'propagate': False},
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
    },
}
