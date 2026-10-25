from django.conf import settings
from django.db import models
from django.utils import timezone
from billing.plans import get_plan, PlanDefinition


class Subscription(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('pending', 'Pending Confirmation'),
        ('past_due', 'Past Due'),
        ('canceled', 'Canceled (Active Until Period End)'),
        ('expired', 'Expired'),
        ('refunded', 'Refunded'),
    ]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='subscription')
    plan_id = models.CharField(max_length=50, default='free', db_index=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='active', db_index=True)

    provider_name = models.CharField(max_length=50, default='none')
    provider_customer_id = models.CharField(max_length=255, blank=True, db_index=True)
    provider_subscription_id = models.CharField(max_length=255, blank=True, db_index=True)

    current_period_start = models.DateTimeField(default=timezone.now)
    current_period_end = models.DateTimeField(null=True, blank=True, db_index=True)
    cancel_at_period_end = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['provider_name', 'provider_subscription_id']),
        ]

    def __str__(self):
        return f"{self.user.username}: {self.plan_id.upper()} ({self.status})"

    @property
    def plan(self) -> PlanDefinition:
        """Returns the centralized plan definition."""
        return get_plan(self.plan_id)

    @property
    def is_valid_active(self) -> bool:
        """Determines if the subscription grants paid tier entitlements."""
        if self.status in ['active', 'canceled']:
            if self.plan_id == 'free':
                return True
            # For paid plans, check term expiration
            if self.current_period_end and self.current_period_end < timezone.now():
                return False
            return True
        return False

    def can_access_feature(self, feature: str) -> bool:
        """Check if user has entitlement to a feature."""
        if not self.is_valid_active:
            # Revert to free tier features when expired/past due
            free_plan = get_plan('free')
            return getattr(free_plan, feature, False)
        return getattr(self.plan, feature, False)


class UsageRecord(models.Model):
    METRIC_CHOICES = [
        ('tailored_application', 'Tailored Application Generated'),
        ('outreach_pitch_sent', 'Outreach Pitch Sent'),
        ('tracked_job', 'Tracked Job Added'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='usage_records')
    metric = models.CharField(max_length=50, choices=METRIC_CHOICES, db_index=True)
    quantity = models.IntegerField(default=1)
    billing_cycle_start = models.DateTimeField(null=True, blank=True, db_index=True)
    reference_id = models.CharField(max_length=255, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'metric', 'created_at']),
            models.Index(fields=['user', 'metric', 'reference_id']),
        ]

    def __str__(self):
        return f"{self.user.username} - {self.metric}: +{self.quantity}"


class WebhookEvent(models.Model):
    provider = models.CharField(max_length=50, db_index=True)
    event_id = models.CharField(max_length=255, unique=True, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    payload = models.JSONField()
    processed = models.BooleanField(default=False, db_index=True)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Webhook [{self.provider}] {self.event_type} - {self.event_id}"


class PaymentTransaction(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Successful'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payment_transactions')
    provider = models.CharField(max_length=50, db_index=True)
    transaction_reference = models.CharField(max_length=255, unique=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='USD')
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending', db_index=True)
    plan_id = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Tx {self.transaction_reference}: {self.currency} {self.amount} ({self.status})"
