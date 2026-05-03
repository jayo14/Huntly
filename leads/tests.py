from django.test import TestCase
from django.urls import reverse
from .models import Lead, Message

class DashboardTests(TestCase):
    def test_dashboard_view(self):
        response = self.client.get(reverse('leads:dashboard'))
        self.assertEqual(response.status_code, 200)

class LeadTests(TestCase):
    def setUp(self):
        self.lead = Lead.objects.create(business_name="Test Biz", score=85)

    def test_lead_list_view(self):
        response = self.client.get(reverse('leads:lead-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Biz")

    def test_lead_detail_view(self):
        response = self.client.get(reverse('leads:lead-detail', args=[self.lead.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Biz")

class PipelineTests(TestCase):
    def test_pipeline_view(self):
        response = self.client.get(reverse('leads:pipeline'))
        self.assertEqual(response.status_code, 200)
