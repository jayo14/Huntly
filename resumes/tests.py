from django.test import TestCase, Client
from django.urls import reverse, path
from django.contrib.auth.models import User
from .models import Resume, Payment
from . import views
import resumes.urls
import json

# Ensure resume-preview URL pattern exists in tests for template rendering
if not any(getattr(p, 'name', None) == 'resume-preview' for p in resumes.urls.urlpatterns):
    resumes.urls.urlpatterns.append(
        path('<int:pk>/preview/', views.resume_preview_partial, name='resume-preview')
    )

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
        resume = Resume.objects.filter(full_name='John Doe').first()
        self.assertIsNotNone(resume)
        self.assertEqual(resume.user, self.user)

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
        payment = Payment.objects.filter(customer_name='Jane Doe').first()
        self.assertIsNotNone(payment)
        self.assertEqual(payment.user, self.user)


class ResumeTenantIsolationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='user_a', password='password123')
        self.user_b = User.objects.create_user(username='user_b', password='password123')

        self.resume_a = Resume.objects.create(
            user=self.user_a,
            full_name="Alice User A",
            email="alice@test.com"
        )
        self.resume_b = Resume.objects.create(
            user=self.user_b,
            full_name="Bob User B",
            email="bob@test.com"
        )

        self.payment_a = Payment.objects.create(
            user=self.user_a,
            customer_name="Customer A",
            amount=150.00,
            method="transfer"
        )
        self.payment_b = Payment.objects.create(
            user=self.user_b,
            customer_name="Customer B",
            amount=300.00,
            method="cash"
        )

    def test_user_a_cannot_see_user_b_resumes_in_list(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('resumes:resume-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Alice User A")
        self.assertNotContains(response, "Bob User B")

    def test_user_b_cannot_see_user_a_resumes_in_list(self):
        self.client.force_login(self.user_b)
        response = self.client.get(reverse('resumes:resume-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Bob User B")
        self.assertNotContains(response, "Alice User A")

    def test_user_a_cannot_update_user_b_resume(self):
        self.client.force_login(self.user_a)
        # GET
        get_res = self.client.get(reverse('resumes:resume-update', args=[self.resume_b.pk]))
        self.assertEqual(get_res.status_code, 404)

        # POST
        data = {
            'full_name': 'Hacked Bob',
            'email': 'hacked@test.com',
            'technical_skills': [],
            'experiences': [],
            'projects': [],
            'certifications': [],
            'education': []
        }
        post_res = self.client.post(
            reverse('resumes:resume-update', args=[self.resume_b.pk]),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertEqual(post_res.status_code, 404)
        self.resume_b.refresh_from_db()
        self.assertEqual(self.resume_b.full_name, "Bob User B")

    def test_user_a_cannot_download_user_b_resume(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('resumes:resume-download', args=[self.resume_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_user_a_cannot_preview_user_b_resume(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('resumes:resume-preview', args=[self.resume_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_payment_list_isolation(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('resumes:payment-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Customer A")
        self.assertNotContains(response, "Customer B")

        self.client.force_login(self.user_b)
        response_b = self.client.get(reverse('resumes:payment-list'))
        self.assertEqual(response_b.status_code, 200)
        self.assertContains(response_b, "Customer B")
        self.assertNotContains(response_b, "Customer A")
