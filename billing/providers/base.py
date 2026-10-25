from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Any, Optional
from billing.plans import PlanDefinition


@dataclass
class CheckoutSession:
    session_id: str
    checkout_url: str
    provider: str
    metadata: Dict[str, Any]


@dataclass
class NormalizedWebhookEvent:
    event_id: str
    event_type: str  # 'payment_success', 'subscription_created', 'subscription_cancelled', 'payment_failed', 'refund'
    provider: str
    customer_email: str
    provider_customer_id: str
    provider_subscription_id: str
    plan_id: str
    amount: float
    currency: str
    raw_payload: Dict[str, Any]


class BasePaymentAdapter(ABC):
    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name identifier of the provider."""
        pass

    @abstractmethod
    def create_checkout_session(
        self,
        user,
        plan: PlanDefinition,
        success_url: str,
        cancel_url: str,
        currency: str = 'USD'
    ) -> CheckoutSession:
        """Create a hosted checkout session."""
        pass

    @abstractmethod
    def verify_webhook_signature(
        self,
        payload_bytes: bytes,
        headers: Dict[str, str]
    ) -> bool:
        """Verify the cryptographic webhook signature."""
        pass

    @abstractmethod
    def parse_webhook_event(
        self,
        payload_dict: Dict[str, Any]
    ) -> Optional[NormalizedWebhookEvent]:
        """Parse provider-specific JSON into a NormalizedWebhookEvent."""
        pass

    @abstractmethod
    def cancel_subscription(
        self,
        provider_subscription_id: str
    ) -> bool:
        """Cancel subscription with provider."""
        pass
