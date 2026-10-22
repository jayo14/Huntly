import json
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from .models import Resume
from leads.models import JobApplication
from .docx_generator import generate_docx, DocxGenerationError


class ResumeTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client = Client()
        self.client.login(username='testuser', password='password123')

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
            'tagline': 'Full-Stack Developer',
            'technical_skills': [{'category': 'Languages', 'skills': 'Python, TypeScript'}],
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

    def test_resume_download_view_success(self):
        resume = Resume.objects.create(
            user=self.user,
            full_name='Alice Smith',
            email='alice@example.com',
            tagline='Software Engineer',
            technical_skills=['Python', 'Django'],
            experiences=[],
            projects=[],
            certifications=[],
            education=[]
        )
        response = self.client.get(reverse('resumes:resume-download', kwargs={'pk': resume.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        self.assertGreater(len(response.content), 100)

    def test_resume_download_with_tailored_job(self):
        resume = Resume.objects.create(
            user=self.user,
            full_name='Alice Smith',
            email='alice@example.com',
            summary='Experienced backend engineer.'
        )
        job = JobApplication.objects.create(
            user=self.user,
            company_name='Stripe',
            role_title='Senior Python Engineer',
            tailored_resume_text='• Tailored Stripe bullet point'
        )
        response = self.client.get(f"{reverse('resumes:resume-download', kwargs={'pk': resume.pk})}?job_id={job.pk}")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
        )
        self.assertGreater(len(response.content), 100)

    @patch('resumes.views.generate_docx')
    def test_resume_download_generator_error(self, mock_generate):
        mock_generate.side_effect = DocxGenerationError("Generation failed")
        resume = Resume.objects.create(
            user=self.user,
            full_name='Alice Smith',
            email='alice@example.com'
        )
        response = self.client.get(reverse('resumes:resume-download', kwargs={'pk': resume.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('resumes:resume-list'), fetch_redirect_response=False)
        messages = list(get_messages(response.wsgi_request))
        self.assertTrue(any("Failed to generate resume document." in m.message for m in messages))

    @patch('resumes.views.generate_docx')
    def test_resume_create_generator_error(self, mock_generate):
        mock_generate.side_effect = DocxGenerationError("Generation failed")
        data = {
            'full_name': 'Error User',
            'email': 'error@example.com'
        }
        response = self.client.post(
            reverse('resumes:resume-create'),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 500)


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
        get_res = self.client.get(reverse('resumes:resume-update', args=[self.resume_b.pk]))
        self.assertEqual(get_res.status_code, 404)

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
