from django.conf import settings
from .base import BasePaymentAdapter
from .mock_provider import MockPaymentAdapter
from .paystack import PaystackAdapter
from .stripe_provider import StripeAdapter


def get_payment_adapter(provider_override: str = None) -> BasePaymentAdapter:
    """Return the configured payment provider adapter."""
    provider_name = (provider_override or getattr(settings, 'HUNTLY_PAYMENT_PROVIDER', 'mock')).lower()

    if provider_name == 'paystack':
        return PaystackAdapter()
    elif provider_name == 'stripe':
        return StripeAdapter()
    else:
        return MockPaymentAdapter()
