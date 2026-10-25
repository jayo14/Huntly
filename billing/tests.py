import hmac
import hashlib
import json
import uuid
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from billing.models import Subscription, UsageRecord, WebhookEvent, PaymentTransaction
from billing.plans import get_plan
from billing.providers.mock_provider import MockPaymentAdapter
from billing.services import (
    get_or_create_subscription,
    get_user_entitlements,
    check_and_consume_tailored_application,
    check_tracked_job_limit,
    check_and_consume_outreach_pitch,
    process_webhook_payload,
)
from leads.models import JobApplication


class BillingAndEntitlementsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='sub_user', email='sub_user@example.com', password='password123')
        self.other_user = User.objects.create_user(username='other_user', email='other_user@example.com', password='password123')
        self.client.force_login(self.user)
        self.mock_adapter = MockPaymentAdapter(secret_key="test_secret_key_123")

    def test_default_free_tier_entitlements(self):
        subscription = get_or_create_subscription(self.user)
        self.assertEqual(subscription.plan_id, 'free')
        self.assertEqual(subscription.status, 'active')

        entitlements = get_user_entitlements(self.user)
        self.assertEqual(entitlements['tailored_applications_limit'], 3)
        self.assertEqual(entitlements['tailored_applications_used'], 0)
        self.assertEqual(entitlements['tracked_jobs_limit'], 25)
        self.assertEqual(entitlements['pitches_limit'], 0)
        self.assertTrue(entitlements['can_export_docx'])
        self.assertFalse(entitlements['can_export_pdf'])

    def test_consume_tailored_application_idempotency_and_quota(self):
        # Consume 1st application
        ok1, msg1 = check_and_consume_tailored_application(self.user, job_application_id=1, version=1)
        self.assertTrue(ok1)
        self.assertEqual(UsageRecord.objects.filter(user=self.user).count(), 1)

        # Same application and version re-run (idempotent, does not consume second credit)
        ok1_repeat, _ = check_and_consume_tailored_application(self.user, job_application_id=1, version=1)
        self.assertTrue(ok1_repeat)
        self.assertEqual(UsageRecord.objects.filter(user=self.user).count(), 1)

        # Consume 2nd application
        ok2, _ = check_and_consume_tailored_application(self.user, job_application_id=2, version=1)
        self.assertTrue(ok2)

        # Consume 3rd application
        ok3, _ = check_and_consume_tailored_application(self.user, job_application_id=3, version=1)
        self.assertTrue(ok3)

        # Attempt 4th application on free tier (quota exceeded)
        ok4, msg4 = check_and_consume_tailored_application(self.user, job_application_id=4, version=1)
        self.assertFalse(ok4)
        self.assertIn("used all 3 free tailored applications", msg4)

    def test_tracked_job_limit_enforcement(self):
        # Create 25 jobs
        for i in range(25):
            JobApplication.objects.create(
                user=self.user,
                company_name=f'Company {i}',
                role_title='Role',
                status='saved'
            )

        allowed, msg = check_tracked_job_limit(self.user)
        self.assertFalse(allowed)
        self.assertIn("reached the maximum of 25 tracked jobs", msg)

        # Archive 1 job
        job0 = JobApplication.objects.filter(user=self.user).first()
        job0.is_archived = True
        job0.save()

        # Now active count is 24, so adding another is allowed
        allowed_after, _ = check_tracked_job_limit(self.user)
        self.assertTrue(allowed_after)

    def test_outreach_pitch_blocked_on_free_tier(self):
        ok, msg = check_and_consume_outreach_pitch(self.user, job_application_id=1, recipient_email='hiring@corp.com')
        self.assertFalse(ok)
        self.assertIn("requires a paid plan", msg)

    def test_webhook_cryptographic_signature_verification(self):
        payload = {
            "event": "charge.success",
            "id": f"evt_{uuid.uuid4().hex[:12]}",
            "data": {
                "id": "ch_12345",
                "customer": {"email": self.user.email, "id": "cus_999"},
                "plan_id": "job_sprint",
                "amount": 9.00,
                "currency": "USD"
            }
        }
        payload_bytes = json.dumps(payload).encode('utf-8')

        # 1. Invalid signature should be rejected (403)
        res_invalid = self.client.post(
            reverse('billing:webhook', args=['mock']),
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_MOCK_SIGNATURE='forged_invalid_signature'
        )
        self.assertEqual(res_invalid.status_code, 403)

        # 2. Valid signature succeeds
        valid_sig = hmac.new(b"mock_secret_key_12345", payload_bytes, hashlib.sha256).hexdigest()
        res_valid = self.client.post(
            reverse('billing:webhook', args=['mock']),
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_MOCK_SIGNATURE=valid_sig
        )
        self.assertEqual(res_valid.status_code, 200)

        # Verify subscription was activated
        sub = Subscription.objects.get(user=self.user)
        self.assertEqual(sub.plan_id, 'job_sprint')
        self.assertEqual(sub.status, 'active')
        self.assertIsNotNone(sub.current_period_end)

        # Verify transaction logged
        self.assertTrue(PaymentTransaction.objects.filter(user=self.user, plan_id='job_sprint', status='success').exists())

    def test_webhook_idempotency_deduplication(self):
        event_id = f"evt_idemp_{uuid.uuid4().hex[:10]}"
        payload = {
            "event": "charge.success",
            "id": event_id,
            "data": {
                "id": "ch_777",
                "customer": {"email": self.user.email},
                "plan_id": "pro_hunter",
                "amount": 19.00,
                "currency": "USD"
            }
        }
        payload_bytes = json.dumps(payload).encode('utf-8')
        valid_sig = hmac.new(b"mock_secret_key_12345", payload_bytes, hashlib.sha256).hexdigest()

        # First call
        self.client.post(
            reverse('billing:webhook', args=['mock']),
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_MOCK_SIGNATURE=valid_sig
        )
        tx_count_1 = PaymentTransaction.objects.filter(user=self.user).count()
        self.assertEqual(tx_count_1, 1)

        # Second call with identical event_id (replay / duplicate webhook)
        self.client.post(
            reverse('billing:webhook', args=['mock']),
            data=payload_bytes,
            content_type='application/json',
            HTTP_X_MOCK_SIGNATURE=valid_sig
        )
        tx_count_2 = PaymentTransaction.objects.filter(user=self.user).count()
        self.assertEqual(tx_count_2, 1)  # No duplicate transaction created

    def test_webhook_subscription_cancellation_and_refund(self):
        sub = get_or_create_subscription(self.user)
        sub.plan_id = 'pro_hunter'
        sub.status = 'active'
        sub.current_period_end = timezone.now() + timezone.timedelta(days=20)
        sub.save()

        # 1. Cancellation webhook event
        cancel_payload = {
            "event": "subscription.cancelled",
            "id": f"evt_cancel_{uuid.uuid4().hex[:8]}",
            "data": {"customer": {"email": self.user.email}, "id": "sub_123"}
        }
        cancel_bytes = json.dumps(cancel_payload).encode('utf-8')
        sig = hmac.new(b"mock_secret_key_12345", cancel_bytes, hashlib.sha256).hexdigest()

        self.client.post(
            reverse('billing:webhook', args=['mock']),
            data=cancel_bytes,
            content_type='application/json',
            HTTP_X_MOCK_SIGNATURE=sig
        )
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'canceled')
        self.assertTrue(sub.cancel_at_period_end)
        # Still retains active paid entitlements until period end
        self.assertTrue(sub.is_valid_active)

        # 2. Refund webhook event
        refund_payload = {
            "event": "charge.refunded",
            "id": f"evt_rf_{uuid.uuid4().hex[:8]}",
            "data": {"customer": {"email": self.user.email}, "amount": 19.00, "currency": "USD"}
        }
        refund_bytes = json.dumps(refund_payload).encode('utf-8')
        rf_sig = hmac.new(b"mock_secret_key_12345", refund_bytes, hashlib.sha256).hexdigest()

        self.client.post(
            reverse('billing:webhook', args=['mock']),
            data=refund_bytes,
            content_type='application/json',
            HTTP_X_MOCK_SIGNATURE=rf_sig
        )
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'refunded')
        self.assertEqual(sub.plan_id, 'free')

    def test_user_data_preserved_when_subscription_ends(self):
        job = JobApplication.objects.create(
            user=self.user,
            company_name='Keep My Data Corp',
            role_title='Lead Architect',
            status='applied'
        )
        sub = get_or_create_subscription(self.user)
        sub.plan_id = 'job_sprint'
        sub.status = 'expired'
        sub.current_period_end = timezone.now() - timezone.timedelta(days=1)
        sub.save()

        # Expired subscription should NOT delete candidate records
        self.assertTrue(JobApplication.objects.filter(pk=job.pk).exists())
        self.assertFalse(sub.is_valid_active)
