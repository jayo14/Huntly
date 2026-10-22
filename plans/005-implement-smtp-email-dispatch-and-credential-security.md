# Plan 005: Implement SMTP Email Dispatch and Secure Credentials

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 5e1e430..HEAD -- leads/views.py leads/forms.py leads/models.py`

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/003-implement-user-multi-tenancy-and-data-isolation.md
- **Category**: correctness
- **Planned at**: commit `5e1e430`, 2026-10-21

## Why this matters

The core value proposition of Huntly is outreach management. However, in `leads/views.py:229-251`, `send_message` creates a database record and updates the lead status to "contacted", but never calls `send_mail` or interacts with an SMTP server. Users believe emails are being delivered when they are not. Additionally, `leads/forms.py:22` sets `render_value=True` on the `email_password` widget, exposing stored passwords in plain text in the rendered HTML source.

## Current state

- `leads/views.py:236-248`:
```python
if subject and body:
    Message.objects.create(
        lead=lead,
        subject=subject,
        body=body
    )
    if lead.status == 'new':
        lead.status = 'contacted'
    lead.last_contacted = timezone.now()
    lead.save()
    messages.success(request, f"Email sent to {lead.business_name}!")
```
- `leads/forms.py:22`:
```python
widgets = {
    'email_password': forms.PasswordInput(render_value=True), # SECURITY: Plaintext password echoed in HTML
    'default_offer': forms.Textarea(attrs={'rows': 3}),
}
```

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run tests | `python3 manage.py test leads` | All tests pass |

## Scope

**In scope**:
- `leads/views.py` (`send_message` view)
- `leads/forms.py` (`AppSettingForm`)
- `leads/tests.py`

**Out of scope**:
- Long-running async queue refactors (e.g. Celery) — this plan implements synchronous dispatch using Django's email backend with clean error handling.

## Steps

1. In `leads/forms.py`:
   - Change `render_value=True` to `render_value=False` (or omit it) so stored passwords are not transmitted in plaintext DOM representations.
   - If user leaves password field blank on update, preserve the existing password instead of wiping it.
2. In `leads/views.py` (`send_message`):
   - Import `from django.core.mail import EmailMessage, get_connection`.
   - Retrieve user's `AppSetting` (scoped to `request.user`).
   - If settings are configured (`smtp_host`, `email_address`, `email_password`):
     - Instantiate `get_connection(backend='django.core.mail.backends.smtp.EmailBackend', host=setting.smtp_host, port=setting.smtp_port, username=setting.email_address, password=setting.email_password, use_tls=True)`.
     - Construct `EmailMessage(subject=subject, body=body, from_email=setting.email_address, to=[lead.email], connection=connection)`.
     - Attempt `.send()`.
     - If sending succeeds: create `Message`, update `lead.status` and `lead.last_contacted`, and add success message.
     - If sending fails: catch exception, do not advance status, and return an informative error message to the user.
   - If settings are not configured or in development mode without credentials: log a warning or use `console.EmailBackend` if specified in settings.
3. In `leads/tests.py`:
   - Use `django.core.mail.outbox` with `locmem.EmailBackend` in tests to assert that calling `send_message` actually places an email in the outbox.
4. Run verification command:
   ```bash
   python3 manage.py test leads
   ```

## STOP conditions

- If network requests hang during tests, ensure `EMAIL_BACKEND = 'django.core.mail.backends.locmem.EmailBackend'` is active in test runner.
