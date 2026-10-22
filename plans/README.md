# Implementation Plans — Huntly Production Readiness

This directory contains self-contained, machine-executable implementation plans designed to resolve all critical security vulnerabilities, architectural bottlenecks, and code smells identified in the repository audit.

## Execution Order & Dependency Graph

```mermaid
flowchart TD
    P001["001: Verification Baseline & Tests"] --> P002["002: Purge Secrets & SQLite DB"]
    P001 --> P003["003: User Multi-Tenancy & Isolation"]
    P003 --> P004["004: Remediate Stored XSS"]
    P003 --> P005["005: Real SMTP Outreach & Credentials"]
    P001 --> P006["006: Production Security Hardening & CSRF"]
    P001 --> P007["007: Robust DOCX Generation"]
    P003 --> P008["008: Optimize Dashboard & Pipeline Queries"]
    P001 --> P009["009: Scraper URL Validation & Resource Safety"]
    P001 --> P010["010: Fix Nanoid CVE & WhiteNoise Static Files"]
```

## Plan Index

| Plan | Priority | Category | Title | Depends On | Status |
|---|---|---|---|---|---|
| [001](001-fix-test-verification-baseline.md) | P1 | tests | Fix Test Verification Baseline and Failing Test Suite | None | DONE |
| [002](002-purge-committed-secrets-and-sqlite-db.md) | P1 | security | Purge Committed Secrets and SQLite DB from Git | 001 | DONE |
| [003](003-implement-user-multi-tenancy-and-data-isolation.md) | P1 | security | Implement User Multi-Tenancy and Data Isolation | 001 | DONE |
| [004](004-remediate-stored-xss-in-message-generator.md) | P1 | security | Remediate Stored XSS in Outreach Message Generator | 003 | DONE |
| [005](005-implement-smtp-email-dispatch-and-credential-security.md) | P2 | correctness | Implement SMTP Email Dispatch and Secure Credentials | 003 | DONE |
| [006](006-harden-production-security-settings-and-csrf.md) | P1 | security | Harden Production Security Settings and CSRF Logout | 001 | DONE |
| [007](007-replace-node-docx-subprocess.md) | P2 | tech-debt | Replace Fragile Node DOCX Subprocess with Robust Generation | 001 | DONE |
| [008](008-optimize-dashboard-and-pipeline-queries.md) | P2 | perf | Optimize Dashboard & Pipeline Queries and Add DB Indexes | 003 | DONE |
| [009](009-scraper-service-safety-and-isolation.md) | P2 | tech-debt | Scraper Service Safety, SSRF Prevention, and Resource Limits | 001 | DONE |
| [010](010-fix-npm-vulnerabilities-and-whitenoise-static-files.md) | P2 | security | Fix NPM Nanoid Vulnerability and Configure WhiteNoise | 001 | DONE |

## Status Vocabulary
- **TODO**: Ready for execution.
- **IN PROGRESS**: Currently being executed in an isolated worktree branch.
- **DONE**: Completed, passed all verification gates and tech lead review.
- **BLOCKED**: Blocked by a STOP condition or unresolved dependency.
