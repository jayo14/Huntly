import json
from unittest.mock import patch
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from .models import Resume
from leads.models import JobApplication
from billing.models import Subscription
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

    def test_user_a_cannot_download_user_b_resume(self):
        self.client.force_login(self.user_a)
        res = self.client.get(reverse('resumes:resume-download', args=[self.resume_b.pk]))
        self.assertEqual(res.status_code, 404)


class MasterCareerProfileWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='careerexpert', password='password123')
        self.client = Client()
        self.client.login(username='careerexpert', password='password123')
        Subscription.objects.create(user=self.user, plan_id='job_sprint', status='active')
        self.job = JobApplication.objects.create(
            user=self.user,
            company_name='Acme Cloud',
            role_title='Staff Backend Engineer',
            job_description='Seeking an experienced Python and PostgreSQL backend engineer. Docker and Kubernetes preferred.',
            status='saved'
        )

    def test_create_master_profile_and_completeness_report(self):
        profile = Resume.objects.create(
            user=self.user,
            full_name='Dr. Katherine Johnson',
            tagline='Senior Calculations Specialist',
            email='katherine@nasa.gov',
            location='Hampton, VA',
            summary='Pioneered celestial mechanics calculations for early space missions with 100% precision.',
            technical_skills=[
                {'name': 'Python, Fortran, Mathematical Modeling', 'category': 'Languages', 'evidence': 'Used across 12 flight trajectories'},
                {'name': 'PostgreSQL, Linux', 'category': 'Systems'}
            ],
            experiences=[
                {
                    'role': 'Lead Aerospace Technologist',
                    'company': 'NASA Langley',
                    'dates': '1953 - 1986',
                    'responsibilities': ['Calculated launch windows and rendezvous paths'],
                    'accomplishments': ['Verified trajectory equations for first crewed spaceflight without error'],
                    'provenance': 'user_entered'
                }
            ],
            projects=[
                {
                    'name': 'Apollo 11 Trajectory Verifier',
                    'contribution': 'Manual verification of digital computer readouts',
                    'outcomes': 'Successfully landed Apollo 11 lunar module',
                    'provenance': 'explicitly_verified'
                }
            ],
            education=[
                {'degree': 'B.S. in Mathematics', 'institution': 'West Virginia State', 'dates': '1937'}
            ],
            is_master=True
        )

        report = profile.get_completeness_report()
        self.assertGreaterEqual(report['score'], 80)
        self.assertTrue(report['is_ready_for_tailoring'])
        self.assertEqual(len(report['missing']), 0)

    def test_multiple_resumes_master_consolidation(self):
        res1 = Resume.objects.create(user=self.user, full_name='Profile 1', email='p1@test.com', is_master=True)
        res2 = Resume.objects.create(user=self.user, full_name='Profile 2', email='p2@test.com', is_master=False)

        # Consolidate res2 as master
        res2.consolidate_as_master()
        res1.refresh_from_db()
        res2.refresh_from_db()

        self.assertFalse(res1.is_master)
        self.assertTrue(res2.is_master)

    def test_resume_docx_and_pdf_generation_binary_structure(self):
        profile = Resume.objects.create(
            user=self.user,
            full_name='Ada Lovelace',
            email='ada@analytical.org',
            summary='Computing pioneer.',
            technical_skills=[{'name': 'Python, SQL', 'category': 'Languages'}],
            experiences=[{'role': 'Architect', 'company': 'Analytical Engine', 'accomplishments': ['Wrote first algorithm']}]
        )

        # 1. Download DOCX
        res_docx = self.client.get(f"{reverse('resumes:resume-download', args=[profile.pk])}?format=docx")
        self.assertEqual(res_docx.status_code, 200)
        self.assertTrue(res_docx.content.startswith(b'PK'), "DOCX must start with valid Office Open XML ZIP signature")
        self.assertEqual(res_docx['Content-Type'], 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')

        # 2. Download PDF
        res_pdf = self.client.get(f"{reverse('resumes:resume-download', args=[profile.pk])}?format=pdf")
        self.assertEqual(res_pdf.status_code, 200)
        self.assertTrue(res_pdf.content.startswith(b'%PDF-'), "PDF must start with valid %PDF- signature")
        self.assertEqual(res_pdf['Content-Type'], 'application/pdf')

    def test_tailored_cover_letter_download_pdf_and_docx(self):
        self.job.cover_letter = "Dear Acme Cloud Team,\nI am thrilled to apply for the Staff Backend Engineer role."
        self.job.save()

        # Cover letter PDF
        res_pdf = self.client.get(f"{reverse('resumes:cover-letter-download', args=[self.job.pk])}?format=pdf")
        self.assertEqual(res_pdf.status_code, 200)
        self.assertTrue(res_pdf.content.startswith(b'%PDF-'))

        # Cover letter DOCX
        res_docx = self.client.get(f"{reverse('resumes:cover-letter-download', args=[self.job.pk])}?format=docx")
        self.assertEqual(res_docx.status_code, 200)
        self.assertTrue(res_docx.content.startswith(b'PK'))

    def test_application_document_versioning_and_snapshot(self):
        from resumes.models import ApplicationDocument
        profile = Resume.objects.create(
            user=self.user,
            full_name='Candidate v1',
            email='cand@test.com',
            summary='Initial summary',
            technical_skills=[{'name': 'Python', 'category': 'Languages'}],
            experiences=[{'role': 'Engineer', 'company': 'StartUp', 'accomplishments': ['Scaled traffic by 50%']}]
        )

        # Generate tailoring v1
        self.client.post(reverse('leads:generate-message', args=[self.job.pk]))
        docs_v1 = ApplicationDocument.objects.filter(job_application=self.job)
        self.assertEqual(docs_v1.count(), 1)
        self.assertEqual(docs_v1.first().version, 1)

        # Generate tailoring v2
        self.client.post(reverse('leads:generate-message', args=[self.job.pk]))
        docs_v2 = ApplicationDocument.objects.filter(job_application=self.job).order_by('-version')
        self.assertEqual(docs_v2.count(), 2)
        self.assertEqual(docs_v2.first().version, 2)
        self.assertEqual(docs_v2.last().version, 1)

    def test_cross_user_isolation_on_document_downloads(self):
        other_user = User.objects.create_user(username='adversary', password='password123')
        other_client = Client()
        other_client.login(username='adversary', password='password123')

        # Adversary attempts to download self.job's cover letter
        res_cl = other_client.get(reverse('resumes:cover-letter-download', args=[self.job.pk]))
        self.assertEqual(res_cl.status_code, 404)

        # Adversary attempts to inspect self.job's document history
        res_hist = other_client.get(reverse('resumes:document-history', args=[self.job.pk]))
        self.assertEqual(res_hist.status_code, 404)

