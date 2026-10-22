from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from .models import JobApplication, Message, AppSetting
from resumes.models import Resume


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

    def test_dashboard_data_scoped_to_user(self):
        other_user = User.objects.create_user(username='otheruser', password='password123')
        JobApplication.objects.create(
            user=other_user, company_name="Other Corp", role_title="Dev", status='applied'
        )

        response = self.client.get(reverse('leads:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_jobs'], 0)
        self.assertEqual(response.context['applied_count'], 0)

    def test_dashboard_funnel_counts_and_percentages(self):
        JobApplication.objects.create(user=self.user, company_name="Co 1", role_title="Dev 1", status='saved')
        JobApplication.objects.create(user=self.user, company_name="Co 2", role_title="Dev 2", status='saved')
        JobApplication.objects.create(user=self.user, company_name="Co 3", role_title="Dev 3", status='applied')
        JobApplication.objects.create(user=self.user, company_name="Co 4", role_title="Dev 4", status='interviewing')
        JobApplication.objects.create(user=self.user, company_name="Co 5", role_title="Dev 5", status='offer')

        response = self.client.get(reverse('leads:dashboard'))
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context['total_jobs'], 5)
        self.assertEqual(response.context['saved_count'], 2)
        self.assertEqual(response.context['applied_count'], 1)
        self.assertEqual(response.context['interviewing_count'], 1)
        self.assertEqual(response.context['offer_count'], 1)

        funnel_dict = {item['label']: (item['count'], item['percentage']) for item in response.context['funnel_stages']}
        self.assertEqual(funnel_dict['Saved'], (2, 40.0))
        self.assertEqual(funnel_dict['Applied'], (1, 20.0))
        self.assertEqual(funnel_dict['Interviewing'], (1, 20.0))
        self.assertEqual(funnel_dict['Offer'], (1, 20.0))


class JobApplicationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='jobseeker', password='password123')
        self.client.force_login(self.user)
        self.job = JobApplication.objects.create(
            user=self.user,
            company_name="Acme Corp",
            role_title="Senior Python Engineer",
            job_description="Seeking a Python and Django expert with PostgreSQL experience.",
            status="saved"
        )

    def test_job_list_view(self):
        response = self.client.get(reverse('leads:lead-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acme Corp")
        self.assertContains(response, "Senior Python Engineer")

    def test_job_detail_view(self):
        response = self.client.get(reverse('leads:lead-detail', args=[self.job.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Acme Corp")

    def test_job_create_view(self):
        response = self.client.post(reverse('leads:lead-create'), {
            'company_name': 'Linear',
            'role_title': 'Frontend Engineer',
            'job_url': 'https://linear.app/careers',
            'job_description': 'React and TypeScript frontend engineer.',
            'status': 'saved'
        })
        self.assertEqual(response.status_code, 302)
        created = JobApplication.objects.filter(company_name='Linear').first()
        self.assertIsNotNone(created)
        self.assertEqual(created.user, self.user)

    def test_job_update_status(self):
        response = self.client.post(reverse('leads:update-status', args=[self.job.pk]), {
            'status': 'interviewing'
        })
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'interviewing')

    def test_job_delete(self):
        response = self.client.post(reverse('leads:lead-delete', args=[self.job.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(JobApplication.objects.filter(pk=self.job.pk).exists())


class PipelineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='piper', password='password123')
        self.client.force_login(self.user)
        JobApplication.objects.create(user=self.user, company_name="Stripe", role_title="Backend Dev", status="applied")
        JobApplication.objects.create(user=self.user, company_name="GitHub", role_title="Platform Eng", status="interviewing")

    def test_pipeline_view(self):
        response = self.client.get(reverse('leads:pipeline'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Stripe")
        self.assertContains(response, "GitHub")
        self.assertContains(response, "Funnel")
        self.assertContains(response, "Kanban")


class TailoringAndOutreachTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='tailoruser', password='password123')
        self.client.force_login(self.user)
        self.resume = Resume.objects.create(
            user=self.user,
            full_name="Jane Developer",
            tagline="Lead Software Engineer",
            summary="10 years building distributed Python and Django backends."
        )
        self.job = JobApplication.objects.create(
            user=self.user,
            company_name="Netflix",
            role_title="Senior Backend Engineer",
            job_description="We need a Python engineer with AWS, Docker, and Kubernetes expertise to build microservices.",
            contact_email="hiring@netflix.com",
            status="saved"
        )

    def test_generate_tailored_message(self):
        response = self.client.post(reverse('leads:generate-message', args=[self.job.pk]))
        self.assertEqual(response.status_code, 200)
        self.job.refresh_from_db()

        self.assertIn("Python", self.job.matched_keywords)
        self.assertIn("AWS", self.job.matched_keywords)
        self.assertTrue(len(self.job.tailored_resume_text) > 20)
        self.assertTrue(len(self.job.cover_letter) > 50)
        self.assertTrue(len(self.job.recruiter_pitch) > 20)
        self.assertGreater(self.job.score, 50)

    def test_send_pitch_email(self):
        response = self.client.post(reverse('leads:send-message', args=[self.job.pk]), {
            'subject': 'Jane Developer - Application for Senior Backend Engineer',
            'body': 'Hi, I saw your open role at Netflix. I have 10 years of Python experience.'
        })
        self.assertEqual(response.status_code, 204)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'applied')
        self.assertIsNotNone(self.job.last_contacted)

        msg = Message.objects.filter(job_application=self.job).first()
        self.assertIsNotNone(msg)
        self.assertEqual(msg.subject, 'Jane Developer - Application for Senior Backend Engineer')


class MultiTenantIsolationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='user_a', password='password123')
        self.user_b = User.objects.create_user(username='user_b', password='password123')

        self.job_a = JobApplication.objects.create(
            user=self.user_a, company_name="Company A", role_title="Role A"
        )
        self.job_b = JobApplication.objects.create(
            user=self.user_b, company_name="Company B", role_title="Role B"
        )

    def test_user_a_cannot_view_user_b_job_in_list(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('leads:lead-list'))
        self.assertContains(response, "Company A")
        self.assertNotContains(response, "Company B")

    def test_user_a_cannot_access_user_b_job_detail(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('leads:lead-detail', args=[self.job_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_user_a_cannot_update_user_b_job(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse('leads:lead-update', args=[self.job_b.pk]), {
            'company_name': 'Hacked Co',
            'role_title': 'Hacked Role',
            'status': 'saved'
        })
        self.assertEqual(response.status_code, 404)
        self.job_b.refresh_from_db()
        self.assertEqual(self.job_b.company_name, "Company B")

    def test_user_a_cannot_delete_user_b_job(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse('leads:lead-delete', args=[self.job_b.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(JobApplication.objects.filter(pk=self.job_b.pk).exists())
