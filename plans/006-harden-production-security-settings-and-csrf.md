# Plan 006: Harden Production Security Settings and CSRF Logout

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 5e1e430..HEAD -- huntly/settings/base.py huntly/settings/prod.py core/views.py core/urls.py`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-fix-test-verification-baseline.md
- **Category**: security
- **Planned at**: commit `5e1e430`, 2026-10-21

## Why this matters

The production configuration (`huntly/settings/prod.py`) lacks critical security headers (SSL redirect, HSTS, Secure cookies). Furthermore, in `huntly/settings/base.py:16`, `SECRET_KEY` falls back to an insecure hardcoded default string (`django-insecure-replace-this-in-prod`) if unset, allowing an attacker to forge session cookies and tamper with CSRF tokens. Additionally, `core/views.py:47-50` allows `logout` via HTTP GET requests without CSRF protection, enabling third-party websites to trigger forced logouts via simple `<img src="...">` tags.

## Current state

- `huntly/settings/base.py:16`:
  `SECRET_KEY = env('SECRET_KEY', default='django-insecure-replace-this-in-prod')`
- `huntly/settings/prod.py`:
  No SSL redirection, no HSTS, no Secure session/CSRF cookies.
- `core/views.py:47-50` and `core/urls.py:10`:
  `def logout_view(request): logout(request); return redirect('core:landing')`
  Mapped to `path('logout/', views.logout_view, name='logout')` accepting GET.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Deployment check | `python3 manage.py check --deploy --settings=huntly.settings.prod` | 0 security errors/warnings |
| Run tests | `python3 manage.py test core` | All tests pass |

## Scope

**In scope**:
- `huntly/settings/base.py`
- `huntly/settings/prod.py`
- `core/views.py`
- `core/urls.py`
- `templates/base.html` (logout link/form)
- `core/tests.py`

**Out of scope**:
- Third-party SSO/OAuth integrations.

## Steps

1. In `huntly/settings/base.py`:
   - Remove the insecure default for `SECRET_KEY` in production. In `prod.py`, require `SECRET_KEY = env('SECRET_KEY')` without fallback, failing fast if absent.
2. In `huntly/settings/prod.py`:
   - Add security flags:
     ```python
     SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
     SESSION_COOKIE_SECURE = True
     CSRF_COOKIE_SECURE = True
     SECURE_BROWSER_XSS_FILTER = True
     SECURE_CONTENT_TYPE_NOSNIFF = True
     X_FRAME_OPTIONS = 'DENY'
     SECURE_HSTS_SECONDS = 31536000 # 1 year
     SECURE_HSTS_INCLUDE_SUBDOMAINS = True
     SECURE_HSTS_PRELOAD = True
     SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
     ```
3. In `core/views.py`:
   - Decorate `logout_view` with `@require_POST`:
     ```python
     from django.views.decorators.http import require_POST

     @require_POST
     def logout_view(request):
         logout(request)
         messages.info(request, "You have successfully logged out.")
         return redirect('core:landing')
     ```
4. In `templates/base.html`:
   - Update the logout navigation button from an `<a href="{% url 'core:logout' %}">` link to a `<form method="post" action="{% url 'core:logout' %}">{% csrf_token %}<button type="submit">Logout</button></form>`.
5. In `core/tests.py`:
   - Add test ensuring GET request to `/logout/` is rejected with HTTP 405 Method Not Allowed.
   - Add test ensuring valid POST with CSRF logs out user and redirects to landing page.
6. Run deployment check:
   ```bash
   python3 manage.py check --deploy --settings=huntly.settings.prod
   ```

## STOP conditions

- If `SECURE_SSL_REDIRECT` interferes with local dev, verify it is only enabled in `prod.py` (with override via env var `SECURE_SSL_REDIRECT=False` if needed).
