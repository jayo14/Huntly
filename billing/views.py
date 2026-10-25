import json
import logging
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse, HttpResponseForbidden
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from billing.models import Subscription, PaymentTransaction, UsageRecord
from billing.plans import get_all_plans, get_plan
from billing.providers import get_payment_adapter
from billing.services import (
    get_or_create_subscription,
    get_user_entitlements,
    process_webhook_payload,
)

logger = logging.getLogger(__name__)


@login_required
def billing_dashboard(request):
    """Subscription and usage management dashboard."""
    entitlements = get_user_entitlements(request.user)
    transactions = PaymentTransaction.objects.filter(user=request.user).order_by('-created_at')[:10]
    plans = get_all_plans()

    context = {
        'entitlements': entitlements,
        'subscription': entitlements['subscription'],
        'current_plan': entitlements['plan'],
        'transactions': transactions,
        'plans': plans,
    }
    return render(request, 'billing/dashboard.html', context)


@login_required
@require_POST
def create_checkout(request, plan_id):
    """Initiate a hosted checkout session for a selected paid plan."""
    if plan_id not in ['job_sprint', 'pro_hunter']:
        messages.error(request, "Invalid plan selection.")
        return redirect('billing:dashboard')

    plan = get_plan(plan_id)
    adapter = get_payment_adapter()

    success_url = request.build_absolute_uri(reverse('billing:checkout-success'))
    cancel_url = request.build_absolute_uri(reverse('billing:dashboard'))

    try:
        session = adapter.create_checkout_session(
            user=request.user,
            plan=plan,
            success_url=success_url,
            cancel_url=cancel_url,
            currency='USD'
        )
        # Record pending subscription state
        subscription = get_or_create_subscription(request.user)
        if subscription.status != 'active' or subscription.plan_id == 'free':
            subscription.status = 'pending'
            subscription.provider_name = adapter.provider_name
            subscription.save(update_fields=['status', 'provider_name', 'updated_at'])

        return redirect(session.checkout_url)

    except Exception as exc:
        logger.error(f"Checkout initialization failed for user {request.user.pk}: {exc}")
        messages.error(request, f"Unable to initialize payment session: {exc}")
        return redirect('billing:dashboard')


@login_required
def checkout_success(request):
    """
    Client redirect destination after payment.
    Never grants immediate access based on query parameters; informs candidate
    that webhook reconciliation is verifying the transaction.
    """
    messages.info(
        request,
        "Your payment has been received! Our system is confirming transmission with the provider. "
        "Your new tier entitlements will activate immediately upon webhook verification."
    )
    return redirect('billing:dashboard')


@login_required
@require_POST
def cancel_subscription(request):
    """Schedule subscription cancellation at current period end without early termination penalties."""
    subscription = get_or_create_subscription(request.user)
    if subscription.plan_id == 'free' or subscription.status not in ['active', 'past_due']:
        messages.warning(request, "You do not have an active recurring subscription to cancel.")
        return redirect('billing:dashboard')

    adapter = get_payment_adapter(subscription.provider_name)
    adapter.cancel_subscription(subscription.provider_subscription_id)

    subscription.cancel_at_period_end = True
    subscription.status = 'canceled'
    subscription.save(update_fields=['cancel_at_period_end', 'status', 'updated_at'])

    messages.info(
        request,
        f"Your {subscription.plan.name} subscription will remain fully active until "
        f"{subscription.current_period_end.strftime('%B %d, %Y') if subscription.current_period_end else 'the end of your period'}. "
        "No further charges will be billed."
    )
    return redirect('billing:dashboard')


@csrf_exempt
@require_POST
def webhook_receiver(request, provider_name):
    """
    Idempotent, cryptographically verified webhook endpoint for payment providers.
    Supports Paystack, Stripe, and Mock testing providers.
    """
    payload_bytes = request.body
    try:
        json_payload = json.loads(payload_bytes.decode('utf-8')) if payload_bytes else {}
    except ValueError:
        return HttpResponseBadRequest("Invalid JSON payload.")

    # Convert headers to a standard dict
    headers = {k: v for k, v in request.headers.items()}
    # Also include META HTTP headers for compatibility
    for k, v in request.META.items():
        if k.startswith('HTTP_'):
            headers[k] = v

    success, message = process_webhook_payload(
        provider_name=provider_name.lower(),
        payload_bytes=payload_bytes,
        headers=headers,
        json_payload=json_payload
    )

    if not success:
        return HttpResponseForbidden(message)

    return JsonResponse({'status': 'ok', 'message': message})
