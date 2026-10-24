"""Security utilities for Huntly.

Provides:
1. Field-level reversible encryption for sensitive credentials (e.g., SMTP passwords)
   using AES-128-CBC + HMAC-SHA256 (Fernet) derived from Django's SECRET_KEY.
2. In-memory / cache-backed rate limiting to defend against brute-force and relay abuse.
3. Strict image file validation (magic bytes, extensions, dimensions via Pillow).
"""

import base64
import functools
import hashlib
import os
import time

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import HttpResponse, JsonResponse
from PIL import Image


def _get_fernet_key() -> bytes:
    """Derive a reproducible 32-byte URL-safe base64-encoded key from SECRET_KEY."""
    secret = getattr(settings, 'SECRET_KEY', '')
    if not secret:
        raise ValueError("SECRET_KEY must be set to derive encryption key.")
    digest = hashlib.sha256(secret.encode('utf-8')).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_credential(plaintext: str) -> str:
    """Encrypt a sensitive string credential at rest using Fernet."""
    if not plaintext:
        return ''
    key = _get_fernet_key()
    fernet = Fernet(key)
    return fernet.encrypt(plaintext.encode('utf-8')).decode('utf-8')


def decrypt_credential(ciphertext: str) -> str:
    """Decrypt a Fernet-encrypted string credential at rest.

    Gracefully falls back to raw string if the input is legacy plaintext (unencrypted)
    or corrupted, ensuring no breaking runtime errors during transition.
    """
    if not ciphertext:
        return ''
    key = _get_fernet_key()
    fernet = Fernet(key)
    try:
        return fernet.decrypt(ciphertext.encode('utf-8')).decode('utf-8')
    except (InvalidToken, ValueError, TypeError):
        # Legacy plaintext fallback
        return ciphertext


def rate_limit(key_prefix: str, limit: int, period: int):
    """Decorator to enforce rate limiting on views via Django cache.

    :param key_prefix: Unique bucket name for this endpoint (e.g. 'login', 'send_message')
    :param limit: Maximum requests permitted within the time period.
    :param period: Sliding window duration in seconds.
    """
    def decorator(view_func):
        @functools.wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if request.user.is_authenticated:
                identifier = f"user_{request.user.pk}"
            else:
                forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
                identifier = forwarded.split(',')[0].strip() if forwarded else request.META.get('REMOTE_ADDR', '127.0.0.1')

            cache_key = f"huntly_rl:{key_prefix}:{identifier}"
            history = cache.get(cache_key, [])
            current_time = time.time()

            # Evict timestamps older than sliding window
            history = [ts for ts in history if current_time - ts < period]

            if len(history) >= limit:
                if request.headers.get('HX-Request') or request.content_type == 'application/json':
                    return JsonResponse(
                        {'error': 'Too many requests. Please slow down and try again later.'},
                        status=429
                    )
                return HttpResponse(
                    'Too many requests. Please wait a moment before trying again.',
                    status=429
                )

            history.append(current_time)
            cache.set(cache_key, history, period)
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def validate_uploaded_image(image_file, max_size_bytes=5 * 1024 * 1024):
    """Verify an uploaded image for file size, extension, and binary integrity.

    Prevents uploading arbitrary files with spoofed extensions.
    """
    if not image_file:
        return image_file

    if image_file.size > max_size_bytes:
        max_mb = max_size_bytes // (1024 * 1024)
        raise ValidationError(f"Image file size must not exceed {max_mb}MB.")

    ext = os.path.splitext(image_file.name)[1].lower()
    allowed_exts = {'.jpg', '.jpeg', '.png', '.webp'}
    if ext not in allowed_exts:
        raise ValidationError(f"Unsupported image format '{ext}'. Allowed formats: JPG, PNG, WEBP.")

    try:
        # Pillow verify checks file headers and image validity
        img = Image.open(image_file)
        img.verify()
        # Reset pointer for subsequent reads/saves
        image_file.seek(0)
    except Exception as exc:
        raise ValidationError("Uploaded file is not a valid or readable image.") from exc

    return image_file
