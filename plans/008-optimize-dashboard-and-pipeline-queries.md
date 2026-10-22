# Plan 008: Optimize Dashboard & Pipeline Queries and Add DB Indexes

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 5e1e430..HEAD -- leads/views.py leads/models.py`

## Status

- **Priority**: P2
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/003-implement-user-multi-tenancy-and-data-isolation.md
- **Category**: perf
- **Planned at**: commit `5e1e430`, 2026-10-21

## Why this matters

The dashboard view (`leads/views.py:17-69`) runs 8 to 10 separate queries on every single request: it calls `Lead.objects.count()` 3 times, queries each status choice individually in a loop (`Lead.objects.filter(status=status).count()`), and runs separate queries for attention items, messages, and payments. The pipeline view also issues 5 individual queries for each column. As the database grows, this N+1 pattern causes significant page latency. Additionally, key query filter columns lack database indexes.

## Current state

- `leads/views.py:33-47`:
```python
if Lead.objects.count() > 0: # Query 1
    closed_leads = Lead.objects.filter(status='closed').count() # Query 2
    conversion_rate = (closed_leads / Lead.objects.count()) * 100 # Query 3

# Funnel data (global)
funnel_stages = []
global_total = Lead.objects.count() # Query 4
for status, label in Lead.STATUS_CHOICES: # Loops 5 times = 5 more queries!
    count = Lead.objects.filter(status=status).count()
```
- `leads/models.py`:
  `status`, `score`, `next_follow_up`, and `created_at` have no `db_index=True`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Make migrations | `python3 manage.py makemigrations` | Index migrations created |
| Run migrations | `python3 manage.py migrate` | Applied successfully |
| Run tests | `python3 manage.py test leads` | All tests pass |

## Scope

**In scope**:
- `leads/models.py` (add `db_index=True` on filtered fields)
- `leads/views.py` (`dashboard` and `pipeline` views)
- `leads/tests.py`

**Out of scope**:
- Caching layer (Redis/Memcached).

## Steps

1. In `leads/models.py`:
   - Add `db_index=True` to `Lead.status`, `Lead.score`, and `Lead.next_follow_up`.
   - Add `db_index=True` to `Message.sent_at` and `Message.is_reply`.
2. Generate and apply migration:
   ```bash
   python3 manage.py makemigrations leads
   python3 manage.py migrate leads
   ```
3. In `leads/views.py` (`dashboard`):
   - Replace the multiple count queries with a single aggregation query:
     ```python
     status_counts = dict(
         user_leads.values('status')
         .annotate(count=Count('id'))
         .values_list('status', 'count')
     )
     total_leads = sum(status_counts.values())
     closed_leads = status_counts.get('closed', 0)
     conversion_rate = (closed_leads / total_leads * 100) if total_leads > 0 else 0

     funnel_stages = [
         {
             'label': label,
             'count': status_counts.get(status, 0),
             'percentage': round((status_counts.get(status, 0) / total_leads * 100), 0) if total_leads > 0 else 0
         }
         for status, label in Lead.STATUS_CHOICES
     ]
     ```
4. In `leads/views.py` (`pipeline`):
   - Fetch all active leads for the user in a single query: `all_leads = list(Lead.objects.filter(user=request.user).order_by('-score'))`.
   - Group them in Python into status buckets rather than running 5 queries.
5. In `leads/tests.py`:
   - Add test using `with self.assertNumQueries(...)` asserting dashboard query count remains constant regardless of status count.
6. Run tests:
   ```bash
   python3 manage.py test leads
   ```

## STOP conditions

- If query assertion fails due to auth or session queries, account for standard auth queries or test with authenticated user fixture.
