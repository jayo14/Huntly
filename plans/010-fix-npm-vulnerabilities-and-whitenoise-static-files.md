# Plan 010: Fix NPM Nanoid Vulnerability and Configure WhiteNoise

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 5e1e430..HEAD -- package.json huntly/settings/base.py requirements.txt`

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-fix-test-verification-baseline.md
- **Category**: security
- **Planned at**: commit `5e1e430`, 2026-10-21

## Why this matters

1. `npm audit` flags a high-severity denial-of-service advisory (GHSA-28wg-ghj8-5hjv) in `nanoid` bundled with `docx` (`^9.6.1`).
2. In `huntly/settings/base.py:106`, `STATIC_ROOT` is configured, but `whitenoise` is not installed or configured in `MIDDLEWARE`. Without WhiteNoise or an external CDN/S3 bucket, Django in production WSGI environments does not serve static files (CSS, JS, images), leading to broken styles in production deployments outside Vercel's static router.

## Current state

- `package.json`:
  `dependencies: { "docx": "^9.6.1" }`
  `npm audit` reports 1 high severity vulnerability in `nanoid`.
- `huntly/settings/base.py`:
  `STATIC_ROOT = BASE_DIR / 'staticfiles'`, but `whitenoise.middleware.WhiteNoiseMiddleware` is missing from `MIDDLEWARE`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| NPM audit check | `npm audit --package-lock-only` | 0 vulnerabilities found |
| Collectstatic | `python3 manage.py collectstatic --no-input` | Static files collected successfully |
| Check system | `python3 manage.py check` | 0 issues found |

## Scope

**In scope**:
- `package.json` & `package-lock.json`
- `requirements.txt`
- `huntly/settings/base.py`
- `huntly/settings/prod.py`

**Out of scope**:
- HTML template restructuring.

## Steps

1. In `package.json`:
   - Run `npm audit fix` or update `docx` dependency to a version that packages patched `nanoid` (or deduplicate/resolve).
   - Verify `npm audit --package-lock-only` reports 0 vulnerabilities.
2. In `requirements.txt`:
   - Add `whitenoise>=6.6.0`.
3. In `huntly/settings/base.py`:
   - In `MIDDLEWARE`, add WhiteNoise immediately after `SecurityMiddleware`:
     ```python
     MIDDLEWARE = [
         "django.middleware.security.SecurityMiddleware",
         "whitenoise.middleware.WhiteNoiseMiddleware",
         ...
     ]
     ```
   - Configure WhiteNoise compressed storage for production in `huntly/settings/prod.py`:
     ```python
     STORAGES = {
         "staticfiles": {
             "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
         },
     }
     ```
4. Verify by running:
   ```bash
   python3 manage.py check
   python3 manage.py collectstatic --dry-run --no-input
   ```

## STOP conditions

- If `collectstatic` fails due to missing source directories, check `STATICFILES_DIRS` configuration.
