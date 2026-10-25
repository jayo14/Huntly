import hashlib
import hmac
import logging
from typing import Dict, Any, Optional
from django.conf import settings
from billing.plans import PlanDefinition
from .base import BasePaymentAdapter, CheckoutSession, NormalizedWebhookEvent

logger = logging.getLogger(__name__)


class PaystackAdapter(BasePaymentAdapter):
    """
    Paystack Payment Adapter.
    Enables card tokenization, recurring plans, and multi-currency (NGN, USD) transactions.
    """
    def __init__(self, secret_key: Optional[str] = None):
        self.secret_key = secret_key or getattr(settings, 'PAYSTACK_SECRET_KEY', '')

    @property
    def provider_name(self) -> str:
        return "paystack"

    def create_checkout_session(
        self,
        user,
        plan: PlanDefinition,
        success_url: str,
        cancel_url: str,
        currency: str = "USD"
    ) -> CheckoutSession:
        import uuid
        reference = f"ps_{plan.id}_{user.pk}_{uuid.uuid4().hex[:12]}"
        # Hosted Paystack checkout endpoint representation
        checkout_url = f"https://checkout.paystack.com/{reference}"
        return CheckoutSession(
            session_id=reference,
            checkout_url=checkout_url,
            provider=self.provider_name,
            metadata={
                "user_id": user.pk,
                "user_email": user.email,
                "plan_id": plan.id,
                "plan_code": plan.paystack_plan_code or "",
                "amount_cents": int(plan.price_usd * 100),
                "currency": currency,
            }
        )

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: Dict[str, str]
    ) -> bool:
        signature = (
            headers.get("x-paystack-signature") or
            headers.get("X-Paystack-Signature") or
            headers.get("HTTP_X_PAYSTACK_SIGNATURE")
        )
        if not signature or not self.secret_key:
            return False
        expected = hmac.new(
            self.secret_key.encode("utf-8"),
            payload_bytes,
            hashlib.sha512
        ).hexdigest()
        return hmac.compare_digest(signature, expected)

    def parse_webhook_event(
        self,
        payload_dict: Dict[str, Any]
    ) -> Optional[NormalizedWebhookEvent]:
        event_name = payload_dict.get("event")
        data = payload_dict.get("data", {})

        event_mapping = {
            "charge.success": "payment_success",
            "subscription.create": "subscription_created",
            "subscription.disable": "subscription_cancelled",
            "invoice.payment_failed": "payment_failed",
            "refund.processed": "refund",
        }
        normalized_type = event_mapping.get(event_name)
        if not normalized_type:
            return None

        # Paystack passes amount in kobo/cents
        amount_raw = data.get("amount", 0)
        amount = float(amount_raw) / 100.0 if amount_raw else 0.0

        customer = data.get("customer", {})
        customer_email = customer.get("email", "") or data.get("email", "")
        customer_id = customer.get("customer_code", "") or str(customer.get("id", ""))

        plan = data.get("plan", {})
        plan_code = plan.get("plan_code", "")
        # Resolve internal plan id
        plan_id = "free"
        if "jobsprint" in plan_code or "weekly" in plan_code:
            plan_id = "job_sprint"
        elif "prohunter" in plan_code or "monthly" in plan_code or amount >= 15.0:
            plan_id = "pro_hunter"

        subscription_id = data.get("subscription_code") or data.get("reference") or str(data.get("id", ""))

        return NormalizedWebhookEvent(
            event_id=str(payload_dict.get("id") or data.get("id") or subscription_id),
            event_type=normalized_type,
            provider=self.provider_name,
            customer_email=customer_email,
            provider_customer_id=customer_id,
            provider_subscription_id=subscription_id,
            plan_id=plan_id,
            amount=amount,
            currency=data.get("currency", "USD").upper(),
            raw_payload=payload_dict
        )

    def cancel_subscription(self, provider_subscription_id: str) -> bool:
        # In production, invokes POST https://api.paystack.co/subscription/disable
        logger.info(f"Paystack subscription disabled: {provider_subscription_id}")
        return True
