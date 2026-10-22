"""Neon AI Gateway client.

One OpenAI-compatible endpoint for every provider, backed by the credential
``neon env pull`` writes (``NEON_AI_GATEWAY_BASE_URL`` / ``NEON_AI_GATEWAY_TOKEN``).
Because it speaks the OpenAI chat-completions protocol we can call it with
``requests`` — no extra SDK.

The gateway currently requires a paid Neon plan, so every entry point returns
``None`` on *any* failure (unreachable, 402, no models, bad JSON). Callers treat
that as "gateway unavailable" and fall through to Gemini, then to the
deterministic generator. Upgrading the plan makes the gateway take over with no
code change.

Model discovery hits ``GET /v1/models`` once per process and caches the result.
"""

import os
import threading

import requests

DEFAULT_TIMEOUT = 60
_FALLBACK_MODELS = (
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gpt-4o-mini",
    "gpt-4o",
)

_cache_lock = threading.Lock()
_model_cache = None


class AIGatewayUnavailable(Exception):
    """The gateway is not configured, not reachable, or rejected the request."""


def gateway_configured():
    return bool(
        os.environ.get("NEON_AI_GATEWAY_BASE_URL")
        and os.environ.get("NEON_AI_GATEWAY_TOKEN")
    )


def _headers():
    return {
        "Authorization": f"Bearer {os.environ['NEON_AI_GATEWAY_TOKEN']}",
        "Content-Type": "application/json",
    }


def _base_url():
    return os.environ["NEON_AI_GATEWAY_BASE_URL"].rstrip("/")


def available_models():
    """Servable models on this branch, or None when discovery fails."""
    global _model_cache
    with _cache_lock:
        if _model_cache is not None:
            return _model_cache

    try:
        response = requests.get(
            f"{_base_url()}/v1/models", headers=_headers(), timeout=DEFAULT_TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()
        models = [m.get("id") for m in payload.get("data", []) if m.get("id")]
    except Exception:
        return None

    if not models:
        return None

    with _cache_lock:
        _model_cache = models
    return models


def pick_model(preferred=None):
    """Pick a chat model: caller preference, then a known-good default."""
    models = available_models() or []
    if preferred and (not models or preferred in models):
        return preferred
    if not models:
        for candidate in _FALLBACK_MODELS:
            return candidate

    for candidate in _FALLBACK_MODELS:
        if candidate in models:
            return candidate

    for model in models:
        lowered = model.lower()
        if any(tag in lowered for tag in ("chat", "gemini", "gpt", "claude", "llama")):
            return model
    return models[0]


def generate_text(prompt, model=None, temperature=0.4, max_tokens=4096):
    """Chat completion via the gateway. Raises AIGatewayUnavailable on any failure."""
    if not gateway_configured():
        raise AIGatewayUnavailable("NEON_AI_GATEWAY_* env vars are not set.")

    chosen = pick_model(model)
    try:
        response = requests.post(
            f"{_base_url()}/v1/chat/completions",
            headers=_headers(),
            json={
                "model": chosen,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        text = payload["choices"][0]["message"]["content"]
    except Exception as exc:
        # Free-plan gateway answers 402; network/DNS failures land here too.
        raise AIGatewayUnavailable(str(exc)) from exc

    if not text or not str(text).strip():
        raise AIGatewayUnavailable("Gateway returned an empty completion.")
    return str(text).strip()
