from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from .models import Lead, Message


class DashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client.force_login(self.user)

    def test_dashboard_view(self):
        response = self.client.get(reverse('leads:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_view_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse('leads:dashboard'))
        expected_url = f"{reverse(settings.LOGIN_URL)}?next={reverse('leads:dashboard')}"
        self.assertRedirects(response, expected_url)


class LeadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='leaduser', password='password123')
        self.client.force_login(self.user)
        self.lead = Lead.objects.create(business_name="Test Biz", score=85)

    def test_lead_list_view(self):
        response = self.client.get(reverse('leads:lead-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Biz")

    def test_lead_detail_view(self):
        response = self.client.get(reverse('leads:lead-detail', args=[self.lead.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Test Biz")

    def test_lead_list_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse('leads:lead-list'))
        expected_url = f"{reverse(settings.LOGIN_URL)}?next={reverse('leads:lead-list')}"
        self.assertRedirects(response, expected_url)


class PipelineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client.force_login(self.user)

    def test_pipeline_view(self):
        response = self.client.get(reverse('leads:pipeline'))
        self.assertEqual(response.status_code, 200)

    def test_pipeline_view_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse('leads:pipeline'))
        expected_url = f"{reverse(settings.LOGIN_URL)}?next={reverse('leads:pipeline')}"
        self.assertRedirects(response, expected_url)
