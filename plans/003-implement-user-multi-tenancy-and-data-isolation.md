# Plan 003: Implement User Multi-Tenancy and Data Isolation

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 5e1e430..HEAD -- leads/models.py leads/views.py resumes/models.py resumes/views.py`

## Status

- **Priority**: P1
- **Effort**: M
- **Risk**: MED
- **Depends on**: plans/001-fix-test-verification-baseline.md
- **Category**: security
- **Planned at**: commit `5e1e430`, 2026-10-21

## Why this matters

Currently, models in `leads` (`Lead`, `AppSetting`, `AutomationRule`, `ScraperJob`) and `resumes` (`Resume`, `Payment`) have no `user` relationship. All authenticated users share the same leads, can delete each other's data, view other users' financial records, and overwrite shared SMTP credentials. Adding user ownership and scoping querysets is mandatory for production launch.

## Current state

- `leads/models.py`:
  `Lead`, `AppSetting`, `AutomationRule`, and `ScraperJob` define fields without `user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)`.
- `resumes/models.py`:
  `Resume` and `Payment` have no `user` relationship.
- `leads/views.py` and `resumes/views.py`:
  Querysets call `.all()`, e.g., `Lead.objects.all()`, `Resume.objects.all()`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Make migrations | `python3 manage.py makemigrations` | New migration files created |
| Run migrations | `python3 manage.py migrate` | Migrations applied |
| Run tests | `python3 manage.py test leads resumes` | All tests pass |

## Scope

**In scope**:
- `leads/models.py`
- `leads/views.py`
- `resumes/models.py`
- `resumes/views.py`
- `leads/migrations/`
- `resumes/migrations/`
- `leads/tests.py` & `resumes/tests.py` (add isolation test cases)

**Out of scope**:
- Public landing page or authentication login/signup views in `core/`.

## Steps

1. In `leads/models.py`:
   - Import `from django.conf import settings`.
   - Add `user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='leads', null=True, blank=True)` to `Lead`.
   - Add `user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='app_settings', null=True, blank=True)` to `AppSetting`.
   - Add `user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='automation_rules', null=True, blank=True)` to `AutomationRule`.
   - Add `user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='scraper_jobs', null=True, blank=True)` to `ScraperJob`.
2. In `resumes/models.py`:
   - Add `user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='resumes', null=True, blank=True)` to `Resume`.
   - Add `user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payments', null=True, blank=True)` to `Payment`.
3. In `leads/views.py`:
   - Update `dashboard`, `lead_list`, `pipeline`, `settings_view`, `automation_dashboard`, `scraper_dashboard` to filter by `request.user`.
   - When creating instances (`lead_create`, `rule_create`, `scraper_create`), assign `instance.user = request.user` before saving.
   - Use `get_object_or_404(Lead, pk=pk, user=request.user)` to prevent IDOR access across accounts.
4. In `resumes/views.py`:
   - Filter `resume_list` and `payment_list` by `request.user`.
   - In `save_resume_data`, assign `resume.user = request.user`.
   - In `payment_create`, assign `user=request.user`.
   - In `resume_update`, `resume_preview_partial`, `resume_download`, lookup `get_object_or_404(Resume, pk=pk, user=request.user)`.
5. Generate and apply migrations:
   ```bash
   python3 manage.py makemigrations
   python3 manage.py migrate
   ```
6. Add multi-user isolation tests in `leads/tests.py` and `resumes/tests.py` confirming User A cannot see or mutate User B's objects. Run:
   ```bash
   python3 manage.py test leads resumes
   ```

## STOP conditions

- If existing migrations conflict with existing schema or default values, STOP and report.
