# Huntly Production Operations & Launch Runbook

## 1. System Architecture Overview

Huntly is an AI-powered job application strategist and pipeline tracker built on:
- **Application Core**: Django 5.x / Django REST Framework (Python 3.12+).
- **Relational Database**: PostgreSQL 16+ (Hosted on Neon Lakebase with branching & SSL required).
- **Static Assets**: WhiteNoise (`CompressedManifestStaticFilesStorage`) served directly from edge container.
- **Media & Document Storage**: S3-compatible Neon Object Storage / Cloudflare R2 for resume documents and snapshots.
- **Payment Gateway**: Multi-provider architecture with Paystack (African/international cards) and Stripe adapters.
- **AI Tailoring Engine**: Google Gemini Flash / OpenAI gpt-4o-mini with deterministic evidence-grounded fallback.
- **Recruiter Outreach**: Transactional SMTP with AES-256 encrypted credential storage, rate limits, and confirmed human-in-the-loop sending.

---

## 2. Configuration & Environment Variables

Production configuration is strictly isolated in [`huntly/settings/prod.py`](file:///home/codegallantx/moi/Huntly/huntly/settings/prod.py).

### Mandatory Production Secrets:
| Environment Variable | Description | Example / Required Format |
|---|---|---|
| `SECRET_KEY` | 50+ character cryptographic signing key | Strong random string (no default allowed) |
| `DEBUG` | Application debug mode | Must be strictly `False` |
| `ALLOWED_HOSTS` | Whitelisted FQDNs | `huntly.app,www.huntly.app,app.huntly.app` |
| `CSRF_TRUSTED_ORIGINS` | Trusted HTTPS origins | `https://huntly.app,https://www.huntly.app` |
| `DATABASE_URL` | PostgreSQL connection string | `postgresql://user:pass@host/db?sslmode=require` |
| `HUNTLY_PAYMENT_PROVIDER` | Active billing provider | `paystack` or `stripe` |
| `PAYSTACK_SECRET_KEY` | Paystack live API secret | `replace-with-your-paystack-secret-key` |
| `STRIPE_SECRET_KEY` | Stripe live secret key | `replace-with-your-stripe-secret-key` |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing key | `replace-with-your-stripe-webhook-secret` |
| `DEFAULT_FROM_EMAIL` | Outgoing system notifications | `Huntly <notifications@huntly.app>` |

---

## 3. Database Backup & Restore Procedures

### 3.1 Standard Logical Backups (`pg_dump`)
Run daily automated snapshots or prior to applying schema migrations:
```bash
# Dump compressed custom-format backup
pg_dump -Fc "$DATABASE_URL" -f "huntly_backup_$(date +%Y%m%d_%H%M%S).dump"

# Verify backup integrity
pg_restore -l "huntly_backup_*.dump" > /dev/null && echo "Backup verified."
```

### 3.2 Restoring from Logical Backup
```bash
# Target clean recovery database
pg_restore --clean --if-exists --no-owner --no-acl -d "$RECOVERY_DATABASE_URL" "huntly_backup_20261025.dump"
```

### 3.3 Neon Instant Point-in-Time Branch Recovery
Because Huntly uses Neon Lakebase Postgres, disaster recovery can restore state to any exact second without downtime:
```bash
# Create a point-in-time recovery branch at the timestamp before incident
neon branch create \
  --project-id "$NEON_PROJECT_ID" \
  --name recovery-snapshot \
  --parent-timestamp "2026-10-25T12:00:00Z"

# Promote recovery branch to primary default if needed
neon branch set-default --branch-id "<recovery-branch-id>"
```

---

## 4. Database Migrations & Zero-Downtime Rollout

### 4.1 Deployment Migration Rules
1. Never commit model alterations without generating and testing migrations.
2. Verify migration dry run:
   ```bash
   python manage.py makemigrations --check --dry-run
   ```
3. Run migrations before cutting web traffic over to new containers:
   ```bash
   python manage.py migrate --noinput
   ```
4. Backward-compatible schema evolution:
   - When adding new columns, always provide `null=True`, `blank=True`, or a safe default.
   - Never remove or rename columns in a single deploy; use a two-phase rollout (deprecate in v1, remove in v2).

---

## 5. Rollback Procedures

### 5.1 Application Code Rollback
If a fatal software defect is identified post-launch:
1. Revert container deployment to previous stable tag in hosting control plane (e.g. Render, Railway, Kubernetes).
2. Git rollback:
   ```bash
   git revert HEAD
   git push origin main
   ```

### 5.2 Migration Reversal (Schema Rollback)
If an unapplied migration must be reversed:
```bash
# Target the previous migration name in the specific app
python manage.py migrate leads 0004_previous_migration_name
```

---

## 6. Operational Launch Checklists

### 6.1 Pre-Launch Verification
- [ ] `DEBUG=False` verified in live environment.
- [ ] `DATABASE_URL` connects to dedicated production PostgreSQL with TLS/SSL enabled.
- [ ] No SQLite fallback exists in production settings (`huntly/settings/prod.py`).
- [ ] All 5 quality gates pass (`./scripts/run_quality_gate.sh`).
- [ ] Payment webhooks registered and test events processed in sandbox.
- [ ] Security headers active: HSTS (31536000s), X-Frame-Options: DENY, X-Content-Type-Options: nosniff.
- [ ] HTTPS enforcement and secure session cookies verified.
- [ ] Rate limits verified on `/signup/`, `/login/`, `/send-message/`.

### 6.2 Launch Day Monitoring
- [ ] Monitor HTTP 5xx error rate on web application server.
- [ ] Verify transactional email delivery status on outreach requests.
- [ ] Verify incoming webhook logs on `/billing/webhook/<provider>/`.
- [ ] Confirm user signup -> master profile creation -> resume generation funnel completes without error.

### 6.3 Post-Launch Health & Maintenance
- [ ] Review slow query logs (`pg_stat_statements` on PostgreSQL).
- [ ] Prune expired sessions: `python manage.py clearsessions`.
- [ ] Monitor database storage and compute autoscaling metrics.

---

## 7. Incident Response Playbooks

### Playbook A: Webhook Delivery / Payment Desynchronization
**Symptom**: User completes checkout on Paystack/Stripe, but their subscription tier remains `free`.
1. Inspect `billing_webhookevent` records:
   ```sql
   SELECT id, provider, event_type, status, error_message, created_at 
   FROM billing_webhookevent 
   WHERE status = 'failed' 
   ORDER BY created_at DESC LIMIT 10;
   ```
2. Check provider webhook log dashboard (Paystack Dashboard -> Settings -> Webhooks / Stripe Workbench).
3. If signature verification failed, verify that `PAYSTACK_SECRET_KEY` or `STRIPE_WEBHOOK_SECRET` matches the provider configuration.
4. Manually re-process event using `process_webhook_event(event_id)`.

### Playbook B: AI Model Provider Outage or Rate Limit
**Symptom**: User clicks "Tailor Application" and encounters slow responses or provider 429/503 errors.
1. Huntly's service layer automatically catches LLM gateway exceptions.
2. The engine falls back deterministically to `_build_grounded_fallback`, preserving candidate career facts and keyword relevance without throwing 500 errors.
3. Check `generation_method` field on `ApplicationDocument` (`evidence_grounded_deterministic_fallback`).

### Playbook C: SMTP / Email Provider Degradation
**Symptom**: Cold outreach emails failing with `accepted_by_provider` timeouts or 502 Bad Gateway.
1. Huntly records failure status on `Message` model (`status='failed'`) without leaking candidate SMTP passwords.
2. Confirm user's custom SMTP host and port in `AppSetting`.
3. Inform candidate via toast notification to check app password credentials or switch to platform default.
