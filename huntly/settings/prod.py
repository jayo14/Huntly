import os
from django.core.exceptions import ImproperlyConfigured
from .base import *

# In production, SECRET_KEY must be provided explicitly via environment or secret manager
SECRET_KEY = env('SECRET_KEY')
if not SECRET_KEY or SECRET_KEY == 'django-insecure-replace-this-in-prod':
    raise ImproperlyConfigured("A strong, unique SECRET_KEY must be configured in production.")

DEBUG = False

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[])
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("ALLOWED_HOSTS must not be empty in production.")

# Database - strictly requires PostgreSQL in production; no silent SQLite fallback
if 'DATABASE_URL' not in os.environ and 'DATABASE_URL' not in env:
    raise ImproperlyConfigured("DATABASE_URL must be configured with a PostgreSQL connection string in production.")

DATABASES = {
    'default': env.db('DATABASE_URL')
}
if DATABASES['default']['ENGINE'] != 'django.db.backends.postgresql':
    raise ImproperlyConfigured(
        f"Production strictly requires PostgreSQL backend. Found '{DATABASES['default']['ENGINE']}'. "
        "SQLite or local fallback is forbidden in production."
    )

DATABASES['default']['CONN_MAX_AGE'] = env.int('CONN_MAX_AGE', default=600)

# Enforce TLS/SSL for remote PostgreSQL (e.g. Neon, AWS RDS)
if env.bool('DB_SSL_REQUIRE', default=True):
    DATABASES['default'].setdefault('OPTIONS', {})['sslmode'] = 'require'

# CSRF Trusted Origins for HTTPS reverse proxies (Render, Railway, Fly.io, Cloudflare)
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])
if not CSRF_TRUSTED_ORIGINS and ALLOWED_HOSTS:
    for host in ALLOWED_HOSTS:
        h = host.strip()
        if h and h not in ('*', 'localhost', '127.0.0.1'):
            if not h.startswith(('http://', 'https://')):
                CSRF_TRUSTED_ORIGINS.append(f"https://{h}")
            else:
                CSRF_TRUSTED_ORIGINS.append(h)

# Security headers & SSL
SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# Content Security Policy (Basic defense-in-depth)
SECURE_REFERRER_POLICY = 'same-origin'

# WhiteNoise production static file compression and caching.
# Private user media is routed through Neon Object Storage (S3-compatible) when configured
STORAGES = {
    **STORAGES,
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

# Production Email settings (SMTP)
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='Huntly <noreply@huntly.app>')
