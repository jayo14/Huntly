import json
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.urls import reverse, path
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from .models import Resume, Payment
from .docx_generator import generate_docx, DocxGenerationError
from . import views
import resumes.urls

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
        self.assertNotEqual(response.status_code, 200)

    @patch('resumes.views.generate_docx')
    def test_resume_update_generator_error(self, mock_generate):
        mock_generate.side_effect = DocxGenerationError("Generation failed")
        resume = Resume.objects.create(
            user=self.user,
            full_name='Update User',
            email='update@example.com'
        )
        data = {
            'full_name': 'Update User Changed',
            'email': 'update@example.com'
        }
        response = self.client.post(
            reverse('resumes:resume-update', kwargs={'pk': resume.pk}),
            data=json.dumps(data),
            content_type='application/json'
        )
        self.assertEqual(response.status_code, 500)
        self.assertNotEqual(response.status_code, 200)

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


class DocxGeneratorUnitTests(TestCase):
    def test_valid_document_generation_produces_non_empty_bytes(self):
        data = {
            'full_name': 'Test Candidate',
            'email': 'candidate@example.com',
            'tagline': 'Lead Architect',
            'technical_skills': ['Python', 'Docker'],
            'experiences': [],
            'projects': [],
            'certifications': [],
            'education': []
        }
        docx_bytes = generate_docx(data)
        self.assertIsInstance(docx_bytes, bytes)
        self.assertGreater(len(docx_bytes), 100)

    @patch('shutil.which', return_value=None)
    def test_missing_node_raises_error(self, mock_which):
        with self.assertRaises(DocxGenerationError) as ctx:
            generate_docx({'full_name': 'Test Candidate'})
        self.assertIn("Node runtime not available", str(ctx.exception))

    @patch('subprocess.Popen')
    def test_node_script_nonzero_exit_raises_error(self, mock_popen):
        process_mock = MagicMock()
        process_mock.communicate.return_value = (b'', b'Script failure occurred')
        process_mock.returncode = 1
        mock_popen.return_value = process_mock

        with self.assertRaises(DocxGenerationError) as ctx:
            generate_docx({'full_name': 'Test Candidate'})
        self.assertIn("Node script failed with exit code 1", str(ctx.exception))

    @patch('subprocess.Popen')
    def test_empty_or_small_stdout_raises_error(self, mock_popen):
        process_mock = MagicMock()
        process_mock.communicate.return_value = (b'too short', b'')
        process_mock.returncode = 0
        mock_popen.return_value = process_mock

        with self.assertRaises(DocxGenerationError) as ctx:
            generate_docx({'full_name': 'Test Candidate'})
        self.assertIn("invalid or empty", str(ctx.exception))
