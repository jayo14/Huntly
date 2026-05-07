from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from .models import Resume, Payment
import json

class ResumeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password')
        self.client = Client()
        self.client.login(username='testuser', password='password')

    def test_resume_list_view(self):
        response = self.client.get(reverse('resumes:resume-list'))
        self.assertEqual(response.status_code, 200)

    def test_resume_create_view_get(self):
        response = self.client.get(reverse('resumes:resume-create'))
        self.assertEqual(response.status_code, 200)

    def test_resume_create_view_post(self):
        data = {
            'full_name': 'John Doe',
            'email': 'john@example.com',
            'technical_skills': [],
            'experiences': [],
            'projects': [],
            'certifications': [],
            'education': []
        }
        response = self.client.post(
            reverse('resumes:resume-create'),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Resume.objects.filter(full_name='John Doe').exists())

    def test_payment_list_view(self):
        response = self.client.get(reverse('resumes:payment-list'))
        self.assertEqual(response.status_code, 200)

    def test_payment_create(self):
        response = self.client.post(reverse('resumes:payment-create'), {
            'customer_name': 'Jane Doe',
            'amount': 2000,
            'method': 'transfer'
        })
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Payment.objects.filter(customer_name='Jane Doe').exists())
