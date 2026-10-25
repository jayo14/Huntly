import hashlib
import hmac
import uuid
from typing import Dict, Any, Optional
from billing.plans import PlanDefinition
from .base import BasePaymentAdapter, CheckoutSession, NormalizedWebhookEvent


class MockPaymentAdapter(BasePaymentAdapter):
    def __init__(self, secret_key: str = "mock_secret_key_12345"):
        self.secret_key = secret_key

    @property
    def provider_name(self) -> str:
        return "mock"

    def create_checkout_session(
        self,
        user,
        plan: PlanDefinition,
        success_url: str,
        cancel_url: str,
        currency: str = "USD"
    ) -> CheckoutSession:
        session_id = f"mock_sess_{uuid.uuid4().hex[:16]}"
        checkout_url = f"{success_url}?session_id={session_id}&plan={plan.id}"
        return CheckoutSession(
            session_id=session_id,
            checkout_url=checkout_url,
            provider=self.provider_name,
            metadata={
                "user_id": user.pk,
                "user_email": user.email,
                "plan_id": plan.id,
                "price": plan.price_usd,
            }
        )

    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: Dict[str, str]
    ) -> bool:
        signature = headers.get("X-Mock-Signature") or headers.get("HTTP_X_MOCK_SIGNATURE")
        if not signature:
            return False
        expected = hmac.new(
            self.secret_key.encode("utf-8"),
            payload_bytes,
            hashlib.sha256
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
            "subscription.created": "subscription_created",
            "subscription.cancelled": "subscription_cancelled",
            "subscription.disabled": "subscription_cancelled",
            "invoice.payment_failed": "payment_failed",
            "charge.failed": "payment_failed",
            "charge.refunded": "refund",
        }
        normalized_type = event_mapping.get(event_name)
        if not normalized_type:
            return None

        return NormalizedWebhookEvent(
            event_id=str(payload_dict.get("id") or data.get("id") or uuid.uuid4()),
            event_type=normalized_type,
            provider=self.provider_name,
            customer_email=data.get("customer", {}).get("email", "") or data.get("email", ""),
            provider_customer_id=str(data.get("customer", {}).get("id", "") or data.get("customer_id", "")),
            provider_subscription_id=str(data.get("subscription_id") or data.get("id") or ""),
            plan_id=data.get("plan_id") or "pro_hunter",
            amount=float(data.get("amount", 0.0)),
            currency=data.get("currency", "USD").upper(),
            raw_payload=payload_dict
        )

    def cancel_subscription(self, provider_subscription_id: str) -> bool:
        return True
