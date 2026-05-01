from django.test import TestCase, Client
from django.urls import reverse
from .models import Lead

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
