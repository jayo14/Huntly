# Plan 002: Purge Committed Secrets and SQLite DB from Git

> **Executor instructions**: Follow this plan step by step. Run every
> verification command and confirm the expected result before moving to the
> next step. If anything in the "STOP conditions" section occurs, stop and
> report — do not improvise. When done, update the status row for this plan
> in `plans/README.md`.
>
> **Drift check (run first)**: `git diff --stat 5e1e430..HEAD -- .gitignore .env.example`

## Status

- **Priority**: P1
- **Effort**: S
- **Risk**: LOW
- **Depends on**: plans/001-fix-test-verification-baseline.md
- **Category**: security
- **Planned at**: commit `5e1e430`, 2026-10-21

## Why this matters

The repository currently tracks `.env.local` (containing local secret keys and database URLs) and `sqlite.db3` (a 180KB SQLite database containing hashed passwords, lead data, and application settings). Committing databases and environment files risks secret exposure and causes merge conflicts. They must be removed from Git tracking and added to `.gitignore`.

## Current state

- Tracked files in git index:
  ```bash
  $ git ls-files sqlite.db3 .env.local
  .env.local
  sqlite.db3
  ```
- `.gitignore`:
  Lines 7 and 17 only ignore `db.sqlite3` and `.env`, omitting `sqlite.db3`, `*.db3`, `.env.local`, and `.env.*`.

## Commands you will need

| Purpose | Command | Expected on success |
|---|---|---|
| Verify untracked | `git ls-files sqlite.db3 .env.local` | Empty output |
| Check git status | `git status` | Clean status or staged deletions |

## Scope

**In scope**:
- `.gitignore`
- Git index removal for `.env.local` and `sqlite.db3` (`git rm --cached`)
- `.env.example` (ensure all necessary configuration keys are documented with dummy values)

**Out of scope**:
- Do not commit actual credential values into `.env.example`.
- Do not delete local working copies from disk if developer needs them; use `git rm --cached`.

## Steps

1. Untrack sensitive files from the git index:
   ```bash
   git rm --cached sqlite.db3 .env.local
   ```
2. Update `.gitignore`:
   Add patterns for SQLite files and local environment files:
   ```
   *.sqlite3
   *.db3
   .env
   .env.*
   !.env.example
   ```
3. Update `.env.example`:
   Ensure it includes placeholder values for all environment variables expected by `huntly/settings/base.py` and `huntly/settings/prod.py`.
4. Run verification command:
   ```bash
   git ls-files sqlite.db3 .env.local
   ```
   Ensure output is empty.

## STOP conditions

- If `git rm --cached` fails due to uncommitted working tree changes, STOP and report.
