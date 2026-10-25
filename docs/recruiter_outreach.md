# Huntly Recruiter Outreach System Architecture & Documentation

## Overview
Huntly's Recruiter Outreach Engine enables job seekers to generate evidence-grounded, personalized recruiter pitches, review and edit drafts, configure secure custom SMTP providers, explicitly approve outbound transmissions, and maintain an immutable message audit trail.

---

## 1. Provider Setup & Configuration

### Supported Outbound Backends
1. **Custom SMTP (Recommended for candidates)**:
   - Users provide their own SMTP server configuration (`smtp_host`, `smtp_port`, `email_address`, `email_password`).
   - Supports TLS (default port `587`) and SSL (port `465`).
   - Common presets:
     - **Gmail / Google Workspace**: `smtp.gmail.com`, Port `587` (requires 16-character Google App Password with 2FA enabled).
     - **Fastmail**: `smtp.fastmail.com`, Port `465` / `587` (requires App Password).
     - **Custom Corporate / Private Domain**: standard authenticated SMTP.
2. **Platform Default / SES / Postmark**:
   - Falls back to `django.core.mail.backends.smtp.EmailBackend` configured in Django `settings.py` or transactional mail API when user operates in platform-managed mode.

### Safe Connection Verification
- Users can click **Verify SMTP Connection** in the [Settings](file:///home/codegallantx/moi/Huntly/leads/templates/leads/settings.html) panel.
- This initiates an active socket handshake and authentication check via `verify_smtp_settings` without dispatching an actual email message to anyone.
- Successful verification marks `is_verified = True` and records `last_verified_at`.

---

## 2. Rate Limits, Quotas, and Anti-Abuse Protections

1. **Per-User Daily Quotas**:
   - Each candidate has an enforceable `daily_send_limit` (default: 50 emails/day) configured in `AppSetting`.
   - The system checks messages with status in `['accepted_by_provider', 'delivered', 'queued']` sent on the current UTC date.
   - Any attempt to exceed the daily quota raises `QuotaExceededError` and returns `429 Too Many Requests`.

2. **Idempotency & Duplicate Send Shield**:
   - Prevents accidental double-clicks or browser reload duplication.
   - If an identical message (same recipient, subject, and body) was sent by the user within the preceding 5 minutes, `send_approved_outreach` raises `DuplicateSendError` and returns `400 Bad Request`.

3. **Burst Rate Limiting**:
   - Endpoints `@rate_limit('send_message', limit=20, period=60)` and `@rate_limit('generate_message', limit=20, period=60)` protect against script-based flooding.

---

## 3. Privacy, Encryption, and Data Integrity

1. **Encrypted Credentials at Rest**:
   - SMTP passwords are never stored in plaintext. They are encrypted using `cryptography.fernet.Fernet` with the application master key.
   - Decryption occurs only in memory when initializing the SMTP connection socket.

2. **Tenant Isolation**:
   - Every `Message`, `JobApplication`, and `AppSetting` record enforces strict ownership (`user=request.user`).
   - Users cannot view, send, cancel, or record replies for messages belonging to other candidates.

3. **Sanitized Error Logging**:
   - When an SMTP server returns an authentication failure or connection error (e.g., `password=...`), regex scrubbing (`re.sub`) strips any credentials before persisting the error string to `Message.error_message` or writing to logs.

4. **Honest Contact & Verification Tracking**:
   - Placeholder and invented email addresses (e.g. `recruiter@example.com`) are rejected at the service layer.
   - Contacts record explicit verification states:
     - `unverified`: Generic pitch mode for external copying.
     - `user_verified`: Personally researched by candidate.
     - `authorized_source`: Sourced from official job listings.

---

## 4. Message Lifecycle & Known Delivery Limitations

### State Transitions
```
[Draft Created]
       │
       ▼ (User checks confirmation box & clicks Send)
    [Queued]
       │
       ├── (SMTP Handshake Accepted) ────────► [Accepted by Provider]
       │                                              │
       │                                              ├── (Recruiter Replies) ──► [Response Logged]
       │                                              └── (Bounce Webhook)    ──► [Bounced]
       │
       └── (SMTP Connection/Auth Error) ──────► [Failed]
```

### Known Delivery Limitations
- **Accepted by Provider vs. Delivered**:
  Standard SMTP transmission protocol confirms that the sender's mail relay successfully transferred the message to the recipient's mail transfer agent (MTA). It does **not** guarantee inbox delivery, spam filter clearance, or immediate recipient attention. Huntly explicitly surfaces this distinction to candidates.
- **Read Receipts & Tracking**:
  Huntly intentionally omits invasive 1x1 tracking pixels or URL redirect wrappers to preserve candidate privacy and maximize deliverability across enterprise spam filters (e.g., Mimecast, Proofpoint, Microsoft Defender).
- **Manual Reply & Outcome Tracking**:
  Candidates can log recruiter responses, interview invitations, or feedback directly into the outreach timeline using `leads:message-reply`.
