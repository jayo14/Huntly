"""
Test settings configuration for Huntly test suite.
Optimized for deterministic execution, test isolation, and fast hashing.
"""
from .base import *

DEBUG = False
SECRET_KEY = 'huntly-test-insecure-secret-key-for-automated-ci-runs-only'

ALLOWED_HOSTS = ['*']

# Fast password hasher for test execution speed
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Fast in-memory cache for test isolation
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
        'LOCATION': 'huntly-test-cache',
    }
}

# In-memory email backend for capturing sent emails in mail.outbox
EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'

# Deterministic mock payment provider for billing tests
HUNTLY_PAYMENT_PROVIDER = 'mock'

# Test-specific storage: local in-memory/file storage to isolate from cloud S3
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.InMemoryStorage",
    },
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
    },
}
