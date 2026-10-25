import logging
import re
from typing import Optional, Tuple, Dict, Any
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMessage, get_connection
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from leads.models import JobApplication, Message, AppSetting, ApplicationActivity
from resumes.models import Resume

logger = logging.getLogger(__name__)


class OutreachServiceError(Exception):
    """Base exception for recruiter outreach operations."""
    pass


class QuotaExceededError(OutreachServiceError):
    """Raised when user exceeds their daily email quota."""
    pass


class DuplicateSendError(OutreachServiceError):
    """Raised when an identical message was recently sent."""
    pass


class InvalidRecipientError(OutreachServiceError):
    """Raised when recipient contact is missing or invalid."""
    pass


def validate_recipient_email(email_address: str) -> str:
    """Validate and clean recipient email address. Never accepts invalid formats."""
    clean_email = (email_address or '').strip()
    if not clean_email:
        raise InvalidRecipientError("Recipient email address is required to send outreach.")

    # Reject known placeholders or invented addresses
    placeholders = ['recruiter@example.com', 'test@test.com', 'hiring@example.com']
    if clean_email.lower() in placeholders:
        raise InvalidRecipientError(
            f"'{clean_email}' is a placeholder. Please provide a verified recruiter email address."
        )

    try:
        validate_email(clean_email)
    except ValidationError:
        raise InvalidRecipientError(f"'{clean_email}' is not a valid email address.")

    return clean_email


def check_daily_quota(user) -> Tuple[bool, int, int]:
    """Check remaining daily quota for user. Returns (is_allowed, remaining, daily_limit)."""
    setting = AppSetting.objects.filter(user=user).first()
    limit = setting.daily_send_limit if setting else 50

    today = timezone.now().date()
    sent_today = Message.objects.filter(
        user=user,
        status__in=['accepted_by_provider', 'delivered', 'queued'],
        sent_at__date=today
    ).count()

    remaining = max(0, limit - sent_today)
    return (remaining > 0, remaining, limit)


def generate_grounded_pitch(
    resume: Optional[Resume],
    job: JobApplication,
    contact_name: Optional[str] = None,
    contact_role: Optional[str] = None
) -> Dict[str, str]:
    """
    Generate an evidence-grounded, polite outreach pitch.
    Does NOT invent referrals, false familiarity, or unverified achievements.
    If no contact is specified, generates a generic message suitable for copying.
    """
    candidate_name = ""
    if resume and getattr(resume, 'full_name', ''):
        candidate_name = resume.full_name
    elif hasattr(job, 'user') and job.user:
        candidate_name = job.user.get_full_name() or job.user.username

    # Extract verified skills and achievements from resume
    skills = []
    if resume and getattr(resume, 'technical_skills', None):
        raw_skills = resume.technical_skills
        if isinstance(raw_skills, list):
            for s in raw_skills:
                if isinstance(s, dict):
                    name = s.get('name') or s.get('skills') or ''
                    if name:
                        skills.extend([k.strip() for k in name.split(',') if k.strip()])
                elif isinstance(s, str):
                    skills.extend([k.strip() for k in s.split(',') if k.strip()])

    skills_highlight = ", ".join(skills[:3]) if skills else "relevant industry capabilities"

    # Salutation logic: never invent recipient name
    name_to_use = (contact_name or job.contact_name or '').strip()
    role_to_use = (contact_role or getattr(job, 'contact_role', '') or '').strip()

    if name_to_use:
        salutation = f"Dear {name_to_use},"
        connection_reason = f"I am reaching out regarding the {job.role_title} position at {job.company_name}."
    elif role_to_use:
        salutation = f"Dear {job.company_name} {role_to_use},"
        connection_reason = f"I am writing to your team regarding the open {job.role_title} role at {job.company_name}."
    else:
        salutation = f"Dear {job.company_name} Hiring Team,"
        connection_reason = f"I am writing to express my strong interest in the {job.role_title} role at {job.company_name}."

    # Highlight relevant evidence from candidate profile
    achievement_sentence = (
        f"With hands-on experience in {skills_highlight}, my background aligns closely with the core requirements of your engineering team."
        if skills else
        f"My professional experience directly aligns with the technical and collaborative expectations for this role."
    )

    body = (
        f"{salutation}\n\n"
        f"{connection_reason} {achievement_sentence}\n\n"
        f"I have reviewed the role requirements and prepared tailored application documents detailing my specific accomplishments. "
        f"I would welcome the opportunity to discuss how my skill set can support {job.company_name}'s immediate goals.\n\n"
        f"Thank you for your time and consideration.\n\n"
        f"Best regards,\n"
        f"{candidate_name}"
    )

    subject = f"Application: {job.role_title} - {candidate_name}"

    return {
        'subject': subject,
        'body': body,
        'recipient_name': name_to_use,
        'recipient_role': role_to_use,
        'has_verified_recipient': bool(job.contact_email),
    }


def create_or_update_draft(
    user,
    job: JobApplication,
    subject: str,
    body: str,
    recipient_email: str = '',
    recipient_name: str = '',
    recipient_role: str = '',
    follow_up_reminder_at: Optional[Any] = None
) -> Message:
    """Create or update a draft message. Drafting never sends an email."""
    with transaction.atomic():
        message, created = Message.objects.get_or_create(
            user=user,
            job_application=job,
            status='draft',
            defaults={
                'subject': subject.strip(),
                'body': body.strip(),
                'recipient_email': recipient_email.strip(),
                'recipient_name': recipient_name.strip(),
                'recipient_role': recipient_role.strip(),
                'follow_up_reminder_at': follow_up_reminder_at,
            }
        )
        if not created:
            message.subject = subject.strip()
            message.body = body.strip()
            message.recipient_email = recipient_email.strip()
            message.recipient_name = recipient_name.strip()
            message.recipient_role = recipient_role.strip()
            if follow_up_reminder_at is not None:
                message.follow_up_reminder_at = follow_up_reminder_at
            message.save()

        # Update contact info on the job application if provided
        if recipient_email and not job.contact_email:
            job.contact_email = recipient_email.strip()
            job.save(update_fields=['contact_email'])
        if recipient_name and not job.contact_name:
            job.contact_name = recipient_name.strip()
            job.save(update_fields=['contact_name'])
        if recipient_role and not getattr(job, 'contact_role', ''):
            job.contact_role = recipient_role.strip()
            job.save(update_fields=['contact_role'])

    return message


def send_approved_outreach(
    message: Message,
    user,
    confirmed: bool = False
) -> Tuple[bool, str, Message]:
    """
    Send an outreach email after explicit user confirmation.
    Enforces daily quota, anti-duplicate protection, and provider limits.
    Distinguishes draft, queued, accepted_by_provider, and failed.
    """
    if not confirmed:
        raise OutreachServiceError("Explicit user confirmation is required prior to sending.")

    if message.user != user or message.job_application.user != user:
        raise OutreachServiceError("Unauthorized: You do not own this message or application.")

    # Validate recipient
    recipient = validate_recipient_email(message.recipient_email or message.job_application.contact_email)

    # Check daily quota
    is_allowed, remaining, limit = check_daily_quota(user)
    if not is_allowed:
        raise QuotaExceededError(
            f"Daily outreach quota reached ({limit} emails/day). Please upgrade limit or try again tomorrow."
        )

    # Prevent duplicate send within 5 minutes
    recent_duplicate = Message.objects.filter(
        user=user,
        job_application=message.job_application,
        recipient_email=recipient,
        subject=message.subject,
        status__in=['accepted_by_provider', 'delivered', 'queued'],
        sent_at__gte=timezone.now() - timezone.timedelta(minutes=5)
    ).exclude(pk=message.pk).exists()

    if recent_duplicate:
        raise DuplicateSendError(
            "An identical message was already sent to this recipient in the last 5 minutes. "
            "Prevented duplicate send."
        )

    setting = AppSetting.objects.filter(user=user).first()
    from_email = (setting.email_address if setting and setting.email_address else None) or getattr(settings, 'DEFAULT_FROM_EMAIL', 'noreply@huntly.local')
    sender_display = (setting.sender_name if setting and setting.sender_name else '') or user.get_full_name() or user.username
    formatted_from = f"{sender_display} <{from_email}>" if sender_display else from_email

    # Mark as queued
    message.status = 'queued'
    message.recipient_email = recipient
    message.save(update_fields=['status', 'recipient_email'])

    try:
        connection = None
        if setting and setting.provider_type == 'smtp' and setting.smtp_host and setting.email_address and setting.email_password:
            connection = get_connection(
                backend='django.core.mail.backends.smtp.EmailBackend',
                host=setting.smtp_host,
                port=setting.smtp_port,
                username=setting.email_address,
                password=setting.get_decrypted_email_password(),
                use_tls=(setting.smtp_port == 587),
                use_ssl=(setting.smtp_port == 465),
                timeout=10,
            )

        email = EmailMessage(
            subject=message.subject,
            body=message.body,
            from_email=formatted_from,
            to=[recipient],
            connection=connection,
        )

        sent_count = email.send(fail_silently=False)
        if sent_count == 0:
            raise OutreachServiceError("Email provider did not accept message.")

        # Update message state to accepted_by_provider
        now = timezone.now()
        message.status = 'accepted_by_provider'
        message.sent_at = now
        message.error_message = ""
        message.provider_message_id = f"huntly-outreach-{message.pk}-{int(now.timestamp())}"
        message.save(update_fields=['status', 'sent_at', 'error_message', 'provider_message_id'])

        # Update JobApplication status to 'applied' if it was 'saved'
        job = message.job_application
        if job.status == 'saved':
            job.transition_to_status('applied', notes=f"Outreach pitch sent to {recipient}")
        job.last_contacted = now
        job.save(update_fields=['last_contacted', 'updated_at'])

        # Record activity
        job.record_activity(
            'email_sent',
            f"Pitch sent to {recipient} ({message.recipient_name or 'Hiring Team'}). "
            f"Status: Accepted by provider (delivery in progress)."
        )

        # If follow-up reminder is configured, schedule it
        if message.follow_up_reminder_at:
            job.next_follow_up = message.follow_up_reminder_at.date()
            job.save(update_fields=['next_follow_up'])

        return (
            True,
            "Message accepted by email provider. Delivery is in progress.",
            message
        )

    except Exception as exc:
        sanitized_err = re.sub(r'(password|auth|secret)=[^&\s]+', r'\1=***', str(exc), flags=re.IGNORECASE)
        message.status = 'failed'
        message.error_message = sanitized_err
        message.save(update_fields=['status', 'error_message'])

        message.job_application.record_activity(
            'status_change',
            f"Outreach pitch to {recipient} failed: {sanitized_err}"
        )
        logger.warning(f"Outreach send failed for user {user.pk} to {recipient}: {sanitized_err}")
        return (False, f"Delivery attempt failed: {sanitized_err}", message)


def record_manual_reply(
    message: Message,
    user,
    reply_notes: str,
    reply_date: Optional[Any] = None
) -> Message:
    """Record a reply received from recruiter or hiring team."""
    if message.user != user or message.job_application.user != user:
        raise OutreachServiceError("Unauthorized: You do not own this message.")

    reply_time = reply_date or timezone.now()
    message.reply_received_at = reply_time
    message.reply_notes = reply_notes.strip()
    message.is_reply = True
    message.save(update_fields=['reply_received_at', 'reply_notes', 'is_reply'])

    # Record activity
    job = message.job_application
    job.record_activity(
        'status_change',
        f"Recruiter response recorded from {message.recipient_name or message.recipient_email}. Notes: {reply_notes}"
    )

    # Optionally update status to interviewing if appropriate
    if job.status in ['saved', 'applied']:
        job.transition_to_status('interviewing', notes="Response received from outreach pitch")

    return message


def cancel_reminder_or_draft(message: Message, user) -> Message:
    """Cancel a pending draft or remove follow up reminder."""
    if message.user != user or message.job_application.user != user:
        raise OutreachServiceError("Unauthorized: You do not own this message.")

    if message.status == 'draft':
        message.status = 'cancelled'
        message.save(update_fields=['status'])
    elif message.follow_up_reminder_at:
        message.follow_up_reminder_at = None
        message.save(update_fields=['follow_up_reminder_at'])

    return message
