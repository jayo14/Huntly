import logging
from typing import Tuple, Dict, Any, Optional
from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone
from billing.models import Subscription, UsageRecord, WebhookEvent, PaymentTransaction
from billing.plans import get_plan, PlanDefinition
from billing.providers import get_payment_adapter

logger = logging.getLogger(__name__)


class EntitlementError(Exception):
    """Raised when an operation exceeds current subscription entitlements."""
    pass


def get_or_create_subscription(user: User) -> Subscription:
    """Retrieve user subscription, ensuring every user has at least a Free tier record."""
    subscription, created = Subscription.objects.get_or_create(
        user=user,
        defaults={
            'plan_id': 'free',
            'status': 'active',
            'provider_name': 'none',
        }
    )
    return subscription


def get_user_entitlements(user: User) -> Dict[str, Any]:
    """Calculate real-time usage meters and feature entitlements for user."""
    subscription = get_or_create_subscription(user)
    plan = subscription.plan
    now = timezone.now()

    # Determine billing cycle boundary
    cycle_start = None
    if plan.billing_interval != 'lifetime' and subscription.current_period_start:
        cycle_start = subscription.current_period_start

    # Calculate tailored applications usage
    app_usage_qs = UsageRecord.objects.filter(user=user, metric='tailored_application')
    if cycle_start:
        app_usage_qs = app_usage_qs.filter(created_at__gte=cycle_start)
    tailored_apps_used = app_usage_qs.count()

    # Calculate outreach pitch usage
    pitch_usage_qs = UsageRecord.objects.filter(user=user, metric='outreach_pitch_sent')
    if cycle_start:
        pitch_usage_qs = pitch_usage_qs.filter(created_at__gte=cycle_start)
    pitches_used = pitch_usage_qs.count()

    # Calculate active tracked jobs count
    from leads.models import JobApplication
    tracked_jobs_count = JobApplication.objects.filter(user=user, is_archived=False).count()

    return {
        'subscription': subscription,
        'plan': plan,
        'is_active_paid': subscription.is_valid_active and plan.id != 'free',
        'status': subscription.status,
        'current_period_end': subscription.current_period_end,
        'cancel_at_period_end': subscription.cancel_at_period_end,
        'tailored_applications_used': tailored_apps_used,
        'tailored_applications_limit': plan.max_tailored_applications,
        'tailored_applications_remaining': max(0, plan.max_tailored_applications - tailored_apps_used),
        'pitches_used': pitches_used,
        'pitches_limit': plan.max_outreach_pitches_per_period,
        'pitches_remaining': max(0, plan.max_outreach_pitches_per_period - pitches_used),
        'tracked_jobs_count': tracked_jobs_count,
        'tracked_jobs_limit': plan.max_tracked_jobs,
        'can_export_docx': plan.can_export_docx,
        'can_export_pdf': subscription.can_access_feature('can_export_pdf'),
        'has_ats_gap_analysis': subscription.can_access_feature('has_ats_gap_analysis'),
        'has_recruiter_pitch': subscription.can_access_feature('has_recruiter_pitch'),
    }


def check_and_consume_tailored_application(
    user: User,
    job_application_id: int,
    version: int = 1
) -> Tuple[bool, str]:
    """
    Transactionally check and consume a tailored-application credit.
    Idempotent: Identical reference_id will NOT double-charge.
    """
    ref_id = f"job-{job_application_id}-v{version}"

    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get_or_create(
            user=user,
            defaults={'plan_id': 'free', 'status': 'active'}
        )[0]
        plan = subscription.plan

        # Check if already consumed for this specific version/job
        already_consumed = UsageRecord.objects.filter(
            user=user,
            metric='tailored_application',
            reference_id=ref_id
        ).exists()
        if already_consumed:
            return True, "Credit already allocated for this tailored version."

        # Calculate usage within current cycle or lifetime
        usage_qs = UsageRecord.objects.filter(user=user, metric='tailored_application')
        cycle_start = None
        if plan.billing_interval != 'lifetime' and subscription.current_period_start:
            cycle_start = subscription.current_period_start
            usage_qs = usage_qs.filter(created_at__gte=cycle_start)

        current_usage = usage_qs.count()
        if current_usage >= plan.max_tailored_applications:
            if plan.id == 'free':
                msg = (
                    f"You have used all {plan.max_tailored_applications} free tailored applications. "
                    "Upgrade to Job Sprint ($9/wk) or Pro Hunter ($19/mo) to tailor unlimited applications."
                )
            else:
                msg = f"You have reached your limit of {plan.max_tailored_applications} applications for this billing period."
            return False, msg

        # Consume credit
        UsageRecord.objects.create(
            user=user,
            metric='tailored_application',
            quantity=1,
            reference_id=ref_id,
            billing_cycle_start=cycle_start
        )
        return True, "Entitlement granted."


def check_tracked_job_limit(user: User) -> Tuple[bool, str]:
    """Check if user has reached the maximum number of tracked jobs in pipeline."""
    subscription = get_or_create_subscription(user)
    plan = subscription.plan

    from leads.models import JobApplication
    current_count = JobApplication.objects.filter(user=user, is_archived=False).count()

    if current_count >= plan.max_tracked_jobs:
        return False, (
            f"You have reached the maximum of {plan.max_tracked_jobs} tracked jobs on the {plan.name}. "
            "Upgrade to Job Sprint or Pro Hunter for unlimited application pipeline tracking."
        )
    return True, "Under limit."


def check_and_consume_outreach_pitch(
    user: User,
    job_application_id: int,
    recipient_email: str
) -> Tuple[bool, str]:
    """Transactionally verify entitlement and consume an outreach pitch credit."""
    ref_id = f"pitch-job-{job_application_id}-{recipient_email}"

    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get_or_create(
            user=user,
            defaults={'plan_id': 'free', 'status': 'active'}
        )[0]
        plan = subscription.plan

        if plan.max_outreach_pitches_per_period <= 0:
            return False, (
                "Direct recruiter outreach requires a paid plan. "
                "Upgrade to Job Sprint ($9/wk) or Pro Hunter ($19/mo) to unlock cold email pitching."
            )

        cycle_start = subscription.current_period_start
        usage_qs = UsageRecord.objects.filter(
            user=user,
            metric='outreach_pitch_sent'
        )
        if cycle_start:
            usage_qs = usage_qs.filter(created_at__gte=cycle_start)

        current_usage = usage_qs.count()
        if current_usage >= plan.max_outreach_pitches_per_period:
            return False, (
                f"Outreach pitch quota reached ({current_usage}/{plan.max_outreach_pitches_per_period}) for this billing cycle."
            )

        UsageRecord.objects.create(
            user=user,
            metric='outreach_pitch_sent',
            quantity=1,
            reference_id=ref_id,
            billing_cycle_start=cycle_start
        )
        return True, "Outreach credit approved."


def process_webhook_payload(
    provider_name: str,
    payload_bytes: bytes,
    headers: Dict[str, str],
    json_payload: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Authenticate webhook cryptographic signature, deduplicate event_id,
    and update subscription state idempotently.
    """
    adapter = get_payment_adapter(provider_name)

    # 1. Cryptographic signature check
    is_valid = adapter.verify_webhook_signature(payload_bytes, headers)
    if not is_valid:
        logger.warning(f"Rejected webhook with invalid signature from provider '{provider_name}'")
        return False, "Invalid cryptographic webhook signature."

    # 2. Parse normalized event
    normalized_event = adapter.parse_webhook_event(json_payload)
    if not normalized_event:
        logger.info(f"Ignored unhandled webhook event from provider '{provider_name}'")
        return True, "Unhandled event type ignored safely."

    # 3. Deduplication via WebhookEvent table
    with transaction.atomic():
        event_record, created = WebhookEvent.objects.get_or_create(
            event_id=normalized_event.event_id,
            defaults={
                'provider': provider_name,
                'event_type': normalized_event.event_type,
                'payload': json_payload,
                'processed': False,
            }
        )
        if not created and event_record.processed:
            logger.info(f"Idempotent skip: Webhook event {normalized_event.event_id} already processed.")
            return True, "Event already processed idempotently."

        # Find target user by customer email or ID
        user = User.objects.filter(email__iexact=normalized_event.customer_email).first()
        if not user:
            # Check by username if email wasn't found
            user = User.objects.filter(username__iexact=normalized_event.customer_email).first()

        if not user:
            logger.warning(f"Webhook {normalized_event.event_id}: User '{normalized_event.customer_email}' not found.")
            event_record.error_message = f"User '{normalized_event.customer_email}' not found."
            event_record.save(update_fields=['error_message'])
            return True, "User not found; acknowledged."

        subscription = get_or_create_subscription(user)
        plan_def = get_plan(normalized_event.plan_id)

        # 4. State transition
        now = timezone.now()
        if normalized_event.event_type in ['payment_success', 'subscription_created']:
            subscription.plan_id = plan_def.id
            subscription.status = 'active'
            subscription.provider_name = provider_name
            subscription.provider_customer_id = normalized_event.provider_customer_id or subscription.provider_customer_id
            subscription.provider_subscription_id = normalized_event.provider_subscription_id or subscription.provider_subscription_id
            subscription.current_period_start = now
            if plan_def.billing_interval == 'weekly':
                subscription.current_period_end = now + timezone.timedelta(days=7)
            elif plan_def.billing_interval == 'monthly':
                subscription.current_period_end = now + timezone.timedelta(days=30)
            subscription.cancel_at_period_end = False
            subscription.save()

            # Record successful transaction
            PaymentTransaction.objects.create(
                user=user,
                provider=provider_name,
                transaction_reference=f"{normalized_event.event_id}-{now.timestamp()}",
                amount=normalized_event.amount or plan_def.price_usd,
                currency=normalized_event.currency or "USD",
                status='success',
                plan_id=plan_def.id
            )

        elif normalized_event.event_type == 'subscription_cancelled':
            subscription.status = 'canceled'
            subscription.cancel_at_period_end = True
            subscription.save()

        elif normalized_event.event_type == 'payment_failed':
            subscription.status = 'past_due'
            subscription.save()

        elif normalized_event.event_type == 'refund':
            subscription.status = 'refunded'
            subscription.plan_id = 'free'
            subscription.save()

            PaymentTransaction.objects.create(
                user=user,
                provider=provider_name,
                transaction_reference=f"rf_{normalized_event.event_id}-{now.timestamp()}",
                amount=normalized_event.amount or 0.0,
                currency=normalized_event.currency or "USD",
                status='refunded',
                plan_id=subscription.plan_id
            )

        event_record.processed = True
        event_record.save(update_fields=['processed'])

    return True, f"Successfully processed {normalized_event.event_type}."
