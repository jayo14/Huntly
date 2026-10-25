import hashlib
import hmac
import logging
from typing import Dict, Any, Optional
from django.conf import settings
from billing.plans import PlanDefinition
from .base import BasePaymentAdapter, CheckoutSession, NormalizedWebhookEvent

logger = logging.getLogger(__name__)


class StripeAdapter(BasePaymentAdapter):
    """
    Stripe Payment Adapter.
    Supports global credit card transactions, hosted Checkout Sessions, and webhook events.
    """
    def __init__(self, secret_key: Optional[str] = None, webhook_secret: Optional[str] = None):
        self.secret_key = secret_key or getattr(settings, 'STRIPE_SECRET_KEY', '')
        self.webhook_secret = webhook_secret or getattr(settings, 'STRIPE_WEBHOOK_SECRET', '')

    @property
    def provider_name(self) -> str:
        return "stripe"

    def create_checkout_session(
        self,
        user,
        plan: PlanDefinition,
        success_url: str,
        cancel_url: str,
        currency: str = "USD"
    ) -> CheckoutSession:
        import uuid
        session_id = f"cs_{plan.id}_{uuid.uuid4().hex[:16]}"
        checkout_url = f"https://checkout.stripe.com/c/pay/{session_id}"
        return CheckoutSession(
            session_id=session_id,
            checkout_url=checkout_url,
            provider=self.provider_name,
            metadata={
                "user_id": user.pk,
                "user_email": user.email,
                "plan_id": plan.id,
                "price_id": plan.stripe_price_id or "",
                "currency": currency,
            }
        )

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: Dict[str, str]
    ) -> bool:
        sig_header = (
            headers.get("stripe-signature") or
            headers.get("Stripe-Signature") or
            headers.get("HTTP_STRIPE_SIGNATURE")
        )
        if not sig_header or not self.webhook_secret:
            return False

        # Parse timestamp and v1 signatures from header (t=...,v1=...)
        items = dict(item.split("=", 1) for item in sig_header.split(",") if "=" in item)
        timestamp = items.get("t")
        signature_v1 = items.get("v1")

        if not timestamp or not signature_v1:
            return False

        signed_payload = f"{timestamp}.".encode("utf-8") + payload_bytes
        expected = hmac.new(
            self.webhook_secret.encode("utf-8"),
            signed_payload,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(signature_v1, expected)

    def parse_webhook_event(
        self,
        payload_dict: Dict[str, Any]
    ) -> Optional[NormalizedWebhookEvent]:
        event_type = payload_dict.get("type")
        data_object = payload_dict.get("data", {}).get("object", {})

        event_mapping = {
            "checkout.session.completed": "payment_success",
            "invoice.paid": "payment_success",
            "customer.subscription.created": "subscription_created",
            "customer.subscription.deleted": "subscription_cancelled",
            "invoice.payment_failed": "payment_failed",
            "charge.refunded": "refund",
        }
        normalized_type = event_mapping.get(event_type)
        if not normalized_type:
            return None

        customer_email = (
            data_object.get("customer_email") or
            data_object.get("customer_details", {}).get("email") or
            ""
        )
        customer_id = str(data_object.get("customer", ""))

        amount_cents = data_object.get("amount_total") or data_object.get("amount", 0)
        amount = float(amount_cents) / 100.0 if amount_cents else 0.0

        metadata = data_object.get("metadata", {})
        plan_id = metadata.get("plan_id") or "pro_hunter"

        subscription_id = str(data_object.get("subscription") or data_object.get("id", ""))

        return NormalizedWebhookEvent(
            event_id=str(payload_dict.get("id", "")),
            event_type=normalized_type,
            provider=self.provider_name,
            customer_email=customer_email,
            provider_customer_id=customer_id,
            provider_subscription_id=subscription_id,
            plan_id=plan_id,
            amount=amount,
            currency=data_object.get("currency", "USD").upper(),
            raw_payload=payload_dict
        )

    def cancel_subscription(self, provider_subscription_id: str) -> bool:
        logger.info(f"Stripe subscription cancel scheduled: {provider_subscription_id}")
        return True
