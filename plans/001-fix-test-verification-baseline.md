# Plan 001: Fix Test Verification Baseline and Failing Test Suite

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 5e1e430..HEAD -- leads/tests.py core/tests.py`
> If any in-scope file changed since this plan was written, compare the
> "Current state" excerpts against the live code before proceeding; on a
> mismatch, treat it as a STOP condition.

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: none
- **Category**: tests
- **Planned at**: commit `5e1e430`, 2026-10-21

## Why this matters

The test suite in `leads/tests.py` is currently failing because tests issue unauthenticated requests to views decorated with `@login_required` (`dashboard` and `pipeline`), expecting HTTP 200 when Django returns HTTP 302 (redirect to login). Additionally, `core/tests.py` is completely empty. Without a passing, reliable test baseline, no subsequent refactoring or security fixes can be safely verified.

## Current state

- `leads/tests.py`:
```python
class DashboardTests(TestCase):
    def test_dashboard_view(self):
        response = self.client.get(reverse('leads:dashboard'))
        self.assertEqual(response.status_code, 200) # FAILS with 302
```
- `core/tests.py`: Empty file with only boilerplate comments.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Run tests | `python3 manage.py test leads core` | exit 0, all tests pass |
| Check system | `python3 manage.py check` | exit 0, no issues found |

## Scope

**In scope**:
- `leads/tests.py`
- `core/tests.py`

**Out of scope**:
- Do not modify view implementations or model definitions in this plan.
- Do not touch `resumes/tests.py` in this plan.

## Steps

1. In `leads/tests.py`, import `django.contrib.auth.models.User` and authenticate the test client before requesting `@login_required` views.
   - Add a `setUp` method in `DashboardTests` and `PipelineTests` creating a test user and calling `self.client.force_login(self.user)`.
   - Add an unauthenticated test case to verify that unauthenticated requests redirect to `LOGIN_URL`.
2. In `core/tests.py`, add unit tests for `landing_page`, `signup`, `login_view`, and `logout_view`:
   - Verify landing page returns 200 for anonymous user.
   - Verify signup view returns 200 on GET, and creates a user and redirects on valid POST.
   - Verify login view returns 200 on GET, and authenticates user on valid POST.
   - Verify logout view redirects to landing page.
3. Run test verification command:
   ```bash
   python3 manage.py test leads core
   ```
   Confirm all tests pass without errors.

## STOP conditions

- If `manage.py test` fails due to database migration errors, STOP and report.
- If dependencies are missing from the execution environment, STOP and report.
