from django.test import TestCase, Client
from django.urls import reverse
from .models import Lead, Message, FollowUpSchedule
from django.utils import timezone
from datetime import timedelta
from django.core import mail

class LeadCRUDTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.lead = Lead.objects.create(
            business_name="Test Business",
            email="test@example.com",
            status="new"
        )

    def test_lead_list(self):
        response = self.client.get(reverse('leads:lead-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Business")

    def test_lead_create_htmx(self):
        url = reverse('leads:lead-create')
        data = {
            'business_name': 'New Lead',
            'email': 'new@example.com',
            'status': 'new',
            'score': 0,
            'tone': 'professional'
        }
        response = self.client.post(url, data, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 204)
        self.assertTrue(Lead.objects.filter(business_name='New Lead').exists())
        self.assertEqual(response.headers['HX-Trigger'], 'leadsChanged')

    def test_lead_update_status_htmx(self):
        url = reverse('leads:update-status', args=[self.lead.pk])
        response = self.client.post(url, {'status': 'contacted'}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 200)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'contacted')
        self.assertContains(response, 'value="contacted" selected')

    def test_lead_delete_htmx(self):
        url = reverse('leads:lead-delete', args=[self.lead.pk])
        response = self.client.post(url, {}, HTTP_HX_REQUEST='true')
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Lead.objects.filter(pk=self.lead.pk).exists())

class MessageServiceTest(TestCase):
    def setUp(self):
        self.lead = Lead.objects.create(
            business_name="Service Test",
            email="service@example.com",
            contact_name="Tester",
            problem="no leads",
            offer="Lead gen",
            tone="professional"
        )

    def test_message_generation(self):
        from .services import generate_messages_for_lead
        messages = generate_messages_for_lead(self.lead)
        self.assertEqual(len(messages), 3)
        self.assertEqual(self.lead.messages.count(), 3)
        self.assertIn("Service Test", messages[0].subject)

    def test_email_sending_and_scheduling(self):
        from .services import send_lead_email

        message = Message.objects.create(
            lead=self.lead,
            type="initial",
            subject="Initial",
            body="Body"
        )

        success, msg = send_lead_email(message)
        self.assertTrue(success)
        self.assertEqual(len(mail.outbox), 1)

        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'contacted')

        self.assertEqual(FollowUpSchedule.objects.filter(lead=self.lead).count(), 2)

    def test_rate_limiting(self):
        from .services import send_lead_email

        # Create 20 sent messages for today
        for i in range(20):
            Message.objects.create(
                lead=self.lead,
                type="initial",
                subject=f"S{i}",
                body=f"B{i}",
                sent_at=timezone.now()
            )

        new_message = Message.objects.create(
            lead=self.lead,
            type="initial",
            subject="Limited",
            body="Limited Body"
        )

        success, msg = send_lead_email(new_message)
        self.assertFalse(success)
        self.assertIn("Rate limit reached", msg)

class AutomationTest(TestCase):
    def test_followup_task(self):
        from .services import process_followups_task

        lead = Lead.objects.create(
            business_name="Cron Test",
            email="cron@example.com",
            status="contacted"
        )
        # Message to be sent
        msg = Message.objects.create(
            lead=lead,
            type="followup1",
            subject="Follow up 1",
            body="Body 1"
        )
        # Schedule that is due
        schedule = FollowUpSchedule.objects.create(
            lead=lead,
            message_type="followup1",
            scheduled_date=timezone.now().date() - timedelta(days=1),
            sent=False
        )

        result = process_followups_task()
        self.assertIn("Processed 1", result)

        schedule.refresh_from_db()
        self.assertTrue(schedule.sent)
        self.assertEqual(len(mail.outbox), 1)
