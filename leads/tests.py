from django.conf import settings
from django.contrib.auth.models import User
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch
from billing.models import Subscription
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
            summary="10 years building distributed Python and Django backends with AWS, Docker, and Kubernetes microservices.",
            technical_skills=[{"name": "Python, Django, AWS, Docker, Kubernetes, Microservices", "category": "Languages & Cloud"}]
        )
        Subscription.objects.create(user=self.user, plan_id='job_sprint', status='active')
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
        response = self.client.post(
            reverse('leads:send-message', args=[self.job.pk]),
            {
                'subject': 'Jane Developer - Application for Senior Backend Engineer',
                'body': 'Hi, I saw your open role at Netflix. I have 10 years of Python experience.',
                'recipient_email': 'hiring@netflix.com',
                'confirm_send': '1',
            },
            HTTP_HX_REQUEST='true',
        )
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


class SettingsTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='settingsuser', password='password123')

    def test_settings_view_get(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('leads:settings'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'leads/settings.html')
        self.assertIn('form', response.context)

    def test_settings_view_post_valid(self):
        self.client.force_login(self.user)
        data = {
            'smtp_host': 'smtp.custom.com',
            'smtp_port': 465,
            'email_address': 'me@example.com',
            'email_password': 'secretpassword',
            'daily_send_limit': 100,
        }
        response = self.client.post(reverse('leads:settings'), data)
        self.assertRedirects(response, reverse('leads:settings'))
        setting = AppSetting.objects.get(user=self.user)
        self.assertEqual(setting.smtp_host, 'smtp.custom.com')
        self.assertEqual(setting.daily_send_limit, 100)


class SecurityRemediationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='victim', password='password123')
        self.user_b = User.objects.create_user(username='attacker', password='password123')
        self.job_a = JobApplication.objects.create(
            user=self.user_a,
            company_name='Victim Corp',
            role_title='Lead Architect',
            contact_email='recruiter@victim.com',
            status='saved'
        )

    def test_smtp_password_encryption_at_rest(self):
        setting = AppSetting.objects.create(
            user=self.user_a,
            smtp_host='smtp.mailgun.org',
            email_address='outreach@victim.com',
            email_password='super-secret-smtp-password-1234'
        )
        raw_db_password = AppSetting.objects.filter(pk=setting.pk).values_list('email_password', flat=True).first()
        self.assertNotEqual(raw_db_password, 'super-secret-smtp-password-1234')
        self.assertTrue(raw_db_password.startswith('gAAAAA'), "Stored password must be Fernet ciphertext")
        self.assertEqual(setting.get_decrypted_email_password(), 'super-secret-smtp-password-1234')

    def test_cross_user_generate_message_forbidden(self):
        self.client.force_login(self.user_b)
        response = self.client.post(reverse('leads:generate-message', args=[self.job_a.pk]))
        self.assertEqual(response.status_code, 404)

    def test_cross_user_send_message_forbidden(self):
        self.client.force_login(self.user_b)
        response = self.client.post(reverse('leads:send-message', args=[self.job_a.pk]), {
            'subject': 'Spam Subject',
            'body': 'Spam Body',
        })
        self.assertEqual(response.status_code, 404)

    def test_rate_limiting_login_endpoint(self):
        from django.core.cache import cache
        cache.clear()

        for _ in range(15):
            res = self.client.get(reverse('core:login'))
            self.assertEqual(res.status_code, 200)

        rate_limited_res = self.client.get(reverse('core:login'))
        self.assertEqual(rate_limited_res.status_code, 429)

    def test_data_export_endpoint(self):
        self.client.force_login(self.user_a)
        Resume.objects.create(
            user=self.user_a,
            full_name='Victim Candidate',
            email='victim@candidate.com'
        )
        response = self.client.get(reverse('leads:profile-export'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/json')
        data = response.json()
        self.assertIn('user', data)
        self.assertEqual(data['user']['username'], 'victim')
        self.assertIn('job_applications', data)
        self.assertEqual(len(data['job_applications']), 1)
        self.assertEqual(data['job_applications'][0]['company_name'], 'Victim Corp')

    def test_delete_account_invalid_password(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse('leads:profile-delete-account'), {'password': 'wrongpassword'})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(pk=self.user_a.pk).exists())

    def test_delete_account_valid_password_cascades(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse('leads:profile-delete-account'), {'password': 'password123'})
        self.assertEqual(response.status_code, 302)
        self.assertFalse(User.objects.filter(pk=self.user_a.pk).exists())
        self.assertFalse(JobApplication.objects.filter(pk=self.job_a.pk).exists())

    def test_resume_form_uses_json_script_for_xss_protection(self):
        self.client.force_login(self.user_a)
        Resume.objects.create(
            user=self.user_a,
            full_name='XSS </script><script>alert(1)</script>',
            email='xss@test.com'
        )
        response = self.client.get(reverse('resumes:resume-create'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="resume-initial-data"')
        self.assertNotContains(response, '</script><script>alert(1)</script>')


class PipelineWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='jobhunter', password='password123')
        self.other_user = User.objects.create_user(username='otherhunter', password='password123')
        self.client.force_login(self.user)

    def test_save_incomplete_job_record_without_description(self):
        response = self.client.post(reverse('leads:lead-create'), {
            'company_name': 'Anthropic',
            'role_title': 'Research Engineer',
            'location': 'San Francisco, CA',
            'salary': '$220,000',
            'status': 'saved'
        })
        self.assertEqual(response.status_code, 302)
        job = JobApplication.objects.filter(user=self.user, company_name='Anthropic').first()
        self.assertIsNotNone(job)
        self.assertEqual(job.role_title, 'Research Engineer')
        self.assertEqual(job.job_description, '')
        self.assertEqual(job.status, 'saved')
        self.assertEqual(job.activities.count(), 1)
        self.assertEqual(job.activities.first().activity_type, 'created')

    def test_status_transition_records_applied_timestamp_and_activity(self):
        job = JobApplication.objects.create(
            user=self.user,
            company_name='Figma',
            role_title='Product Engineer',
            status='saved'
        )
        self.assertIsNone(job.applied_at)

        response = self.client.post(reverse('leads:update-status', args=[job.pk]), {
            'status': 'applied',
            'notes': 'Submitted via careers portal'
        })
        self.assertEqual(response.status_code, 302)
        job.refresh_from_db()
        self.assertEqual(job.status, 'applied')
        self.assertIsNotNone(job.applied_at)

        activity = job.activities.filter(activity_type='status_change').first()
        self.assertIsNotNone(activity)
        self.assertEqual(activity.from_status, 'saved')
        self.assertEqual(activity.to_status, 'applied')
        self.assertIn('Submitted via careers portal', activity.description)

    def test_invalid_status_transition_rejected(self):
        job = JobApplication.objects.create(
            user=self.user,
            company_name='Linear',
            role_title='Designer',
            status='saved'
        )
        response = self.client.post(reverse('leads:update-status', args=[job.pk]), {
            'status': 'super_accepted'
        })
        self.assertEqual(response.status_code, 400)
        job.refresh_from_db()
        self.assertEqual(job.status, 'saved')

    def test_archive_and_restore_job_application(self):
        job = JobApplication.objects.create(
            user=self.user,
            company_name='Vault Technologies Inc',
            role_title='Architect',
            status='rejected'
        )
        self.assertFalse(job.is_archived)

        # Archive
        self.client.post(reverse('leads:lead-archive', args=[job.pk]))
        job.refresh_from_db()
        self.assertTrue(job.is_archived)

        # Active list excludes archived jobs
        res_active = self.client.get(reverse('leads:lead-list'))
        self.assertNotIn(job, res_active.context['jobs'])

        # Archived view includes them
        res_archived = self.client.get(f"{reverse('leads:lead-list')}?archived=1")
        self.assertIn(job, res_archived.context['jobs'])
        self.assertContains(res_archived, "Vault Technologies Inc")

        # Restore
        self.client.post(reverse('leads:lead-archive', args=[job.pk]))
        job.refresh_from_db()
        self.assertFalse(job.is_archived)

    def test_pipeline_kanban_view_groups_stages(self):
        JobApplication.objects.create(user=self.user, company_name='Co 1', role_title='R1', status='saved')
        JobApplication.objects.create(user=self.user, company_name='Co 2', role_title='R2', status='applied')
        JobApplication.objects.create(user=self.user, company_name='Co 3', role_title='R3', status='interviewing')

        response = self.client.get(reverse('leads:pipeline'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Co 1")
        self.assertContains(response, "Co 2")
        self.assertContains(response, "Co 3")

    def test_dashboard_metrics_accuracy_and_empty_handling(self):
        res_empty = self.client.get(reverse('leads:dashboard'))
        self.assertEqual(res_empty.status_code, 200)
        self.assertEqual(res_empty.context['total_jobs'], 0)
        self.assertEqual(res_empty.context['callback_rate'], 0.0)

        JobApplication.objects.create(user=self.user, company_name='C1', role_title='T1', status='saved')
        JobApplication.objects.create(user=self.user, company_name='C2', role_title='T2', status='applied')
        JobApplication.objects.create(user=self.user, company_name='C3', role_title='T3', status='interviewing')
        JobApplication.objects.create(user=self.user, company_name='C4', role_title='T4', status='offer')

        res_populated = self.client.get(reverse('leads:dashboard'))
        self.assertEqual(res_populated.status_code, 200)
        self.assertEqual(res_populated.context['total_jobs'], 4)
        self.assertEqual(res_populated.context['saved_count'], 1)
        self.assertEqual(res_populated.context['applied_count'], 1)
        self.assertEqual(res_populated.context['interviewing_count'], 1)
        self.assertEqual(res_populated.context['offer_count'], 1)
        self.assertEqual(res_populated.context['callback_rate'], 66.7)


class RecruiterOutreachWorkflowTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='applicant', password='password123')
        self.other_user = User.objects.create_user(username='rival', password='password123')
        Subscription.objects.create(user=self.user, plan_id='job_sprint', status='active')
        self.job = JobApplication.objects.create(
            user=self.user,
            company_name='Stripe',
            role_title='Staff Infrastructure Engineer',
            contact_name='Sarah Jenkins',
            contact_role='Engineering Talent Lead',
            contact_email='sarah.jenkins@stripe.com',
            status='saved'
        )
        self.other_job = JobApplication.objects.create(
            user=self.other_user,
            company_name='Vercel',
            role_title='Frontend Specialist',
            contact_email='recruiter@vercel.com',
            status='saved'
        )
        self.client.force_login(self.user)
        mail.outbox.clear()

    def test_save_pitch_draft_does_not_send_email(self):
        response = self.client.post(reverse('leads:send-message', args=[self.job.pk]), {
            'subject': 'Application: Staff Infrastructure Engineer - John Doe',
            'body': 'Dear Sarah Jenkins, I would love to connect about infrastructure at Stripe.',
            'recipient_email': 'sarah.jenkins@stripe.com',
            'is_draft': '1',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

        message = Message.objects.get(job_application=self.job)
        self.assertEqual(message.status, 'draft')
        self.assertEqual(message.user, self.user)
        self.assertIsNone(message.sent_at)
        self.assertEqual(self.job.status, 'saved')

    def test_send_without_explicit_confirmation_rejected(self):
        response = self.client.post(reverse('leads:send-message', args=[self.job.pk]), {
            'subject': 'Application: Staff Infrastructure Engineer',
            'body': 'Pitch body content here.',
            'recipient_email': 'sarah.jenkins@stripe.com',
            # confirm_send is omitted
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("Explicit user confirmation is required", response.content.decode())
        self.assertEqual(len(mail.outbox), 0)

    def test_send_with_placeholder_or_invalid_email_rejected(self):
        response = self.client.post(reverse('leads:send-message', args=[self.job.pk]), {
            'subject': 'Application: Staff Infrastructure Engineer',
            'body': 'Pitch body content here.',
            'recipient_email': 'recruiter@example.com',
            'confirm_send': '1',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("placeholder", response.content.decode().lower())
        self.assertEqual(len(mail.outbox), 0)

    def test_send_approved_outreach_success_and_state_tracking(self):
        response = self.client.post(reverse('leads:send-message', args=[self.job.pk]), {
            'subject': 'Application: Staff Infrastructure Engineer - Candidate',
            'body': 'Dear Sarah Jenkins, I would welcome a conversation regarding Stripe infrastructure.',
            'recipient_email': 'sarah.jenkins@stripe.com',
            'confirm_send': '1',
            'schedule_follow_up': '2026-11-01',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)

        sent_mail = mail.outbox[0]
        self.assertIn('sarah.jenkins@stripe.com', sent_mail.to)
        self.assertEqual(sent_mail.subject, 'Application: Staff Infrastructure Engineer - Candidate')

        message = Message.objects.get(job_application=self.job)
        self.assertEqual(message.status, 'accepted_by_provider')
        self.assertIsNotNone(message.sent_at)
        self.assertEqual(message.recipient_email, 'sarah.jenkins@stripe.com')

        # Application state transitioned to applied
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'applied')
        self.assertIsNotNone(self.job.applied_at)
        self.assertIsNotNone(self.job.next_follow_up)

        # Timeline activity recorded
        email_activity = self.job.activities.filter(activity_type='email_sent').first()
        self.assertIsNotNone(email_activity)
        self.assertIn('Accepted by provider', email_activity.description)

    def test_quota_exceeded_blocks_send(self):
        # Set daily limit to 1
        AppSetting.objects.create(user=self.user, daily_send_limit=1)

        # Send 1 message
        self.client.post(reverse('leads:send-message', args=[self.job.pk]), {
            'subject': 'First Application',
            'body': 'First outreach pitch.',
            'recipient_email': 'recruiter1@stripe.com',
            'confirm_send': '1',
        })
        self.assertEqual(len(mail.outbox), 1)

        # Create another job to attempt second send
        second_job = JobApplication.objects.create(
            user=self.user,
            company_name='OpenAI',
            role_title='AI Engineer',
            contact_email='recruiter@openai.com',
            status='saved'
        )

        response = self.client.post(reverse('leads:send-message', args=[second_job.pk]), {
            'subject': 'Second Application',
            'body': 'Second outreach pitch.',
            'recipient_email': 'recruiter@openai.com',
            'confirm_send': '1',
        })
        self.assertEqual(response.status_code, 429)
        self.assertIn("Daily outreach quota reached", response.content.decode())
        self.assertEqual(len(mail.outbox), 1)

    def test_duplicate_send_protection(self):
        # Send first message
        self.client.post(reverse('leads:send-message', args=[self.job.pk]), {
            'subject': 'Identical Pitch',
            'body': 'Same body message.',
            'recipient_email': 'sarah.jenkins@stripe.com',
            'confirm_send': '1',
        })
        self.assertEqual(len(mail.outbox), 1)

        # Attempt sending identical message immediately
        response = self.client.post(reverse('leads:send-message', args=[self.job.pk]), {
            'subject': 'Identical Pitch',
            'body': 'Same body message.',
            'recipient_email': 'sarah.jenkins@stripe.com',
            'confirm_send': '1',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn("identical message was already sent", response.content.decode())
        self.assertEqual(len(mail.outbox), 1)

    def test_user_cannot_send_outreach_for_other_users_job(self):
        response = self.client.post(reverse('leads:send-message', args=[self.other_job.pk]), {
            'subject': 'Infiltrate other job',
            'body': 'Hacked message.',
            'recipient_email': 'target@company.com',
            'confirm_send': '1',
        })
        self.assertEqual(response.status_code, 404)
        self.assertEqual(len(mail.outbox), 0)

    def test_record_recruiter_reply_and_notes(self):
        message = Message.objects.create(
            user=self.user,
            job_application=self.job,
            recipient_email='sarah.jenkins@stripe.com',
            subject='Initial Outreach',
            body='Pitch body',
            status='accepted_by_provider'
        )

        response = self.client.post(reverse('leads:message-reply', args=[message.pk]), {
            'reply_notes': 'Invited for recruiter screen next Monday at 2pm.'
        })
        self.assertEqual(response.status_code, 302)

        message.refresh_from_db()
        self.assertTrue(message.is_reply)
        self.assertIsNotNone(message.reply_received_at)
        self.assertIn('recruiter screen', message.reply_notes)

        # Status promoted to interviewing
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'interviewing')

    def test_cancel_reminder_or_draft(self):
        message = Message.objects.create(
            user=self.user,
            job_application=self.job,
            subject='Pending Draft',
            body='Draft body',
            status='draft'
        )
        response = self.client.post(reverse('leads:message-cancel', args=[message.pk]))
        self.assertEqual(response.status_code, 302)
        message.refresh_from_db()
        self.assertEqual(message.status, 'cancelled')

    @patch('leads.services.outreach_service.EmailMessage.send')
    def test_provider_failure_records_failed_status_without_secret_leak(self, mock_send):
        mock_send.side_effect = Exception("SMTP auth failed: password=supersecretpass connection timed out")
        response = self.client.post(reverse('leads:send-message', args=[self.job.pk]), {
            'subject': 'Outreach Pitch',
            'body': 'Pitch content',
            'recipient_email': 'sarah.jenkins@stripe.com',
            'confirm_send': '1',
        })
        self.assertEqual(response.status_code, 502)

        message = Message.objects.get(job_application=self.job)
        self.assertEqual(message.status, 'failed')
        self.assertNotIn('supersecretpass', message.error_message)
        self.assertIn('***', message.error_message)





class JobIntakeServiceTests(TestCase):
    def test_private_and_local_targets_are_rejected(self):
        from .services.job_intake import JobIntakeError, _validate_url

        for url in (
            'http://127.0.0.1/job',
            'http://localhost:8000/job',
            'http://169.254.169.254/latest/meta-data/',
            'http://10.0.0.5/job',
            'file:///etc/passwd',
            'http://user:pass@example.com/job',
        ):
            with self.subTest(url=url), self.assertRaises(JobIntakeError):
                _validate_url(url)

    def test_redirect_hop_is_revalidated(self):
        from .services.job_intake import JobIntakeError, fetch_job_posting

        class RedirectResponse:
            status_code = 302
            headers = {'Location': 'http://127.0.0.1/internal'}
            encoding = 'utf-8'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        with patch('leads.services.job_intake._resolve_public_host', return_value='93.184.216.34'), \
                patch('leads.services.job_intake.requests.get', return_value=RedirectResponse()):
            with self.assertRaises(JobIntakeError):
                fetch_job_posting('https://example.com/job')

    def test_oversized_and_binary_responses_are_rejected(self):
        from .services.job_intake import JobIntakeError, fetch_job_posting

        class FakeResponse:
            def __init__(self, headers, status_code=200):
                self.status_code = status_code
                self.headers = headers
                self.encoding = 'utf-8'

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def iter_content(self, chunk_size):
                return iter([])

        with patch('leads.services.job_intake._resolve_public_host', return_value='93.184.216.34'):
            with patch('leads.services.job_intake.requests.get', return_value=FakeResponse({
                'Content-Type': 'text/html',
                'Content-Length': str(3_000_000),
            })):
                with self.assertRaises(JobIntakeError):
                    fetch_job_posting('https://example.com/job')

            with patch('leads.services.job_intake.requests.get', return_value=FakeResponse({
                'Content-Type': 'application/pdf',
            })):
                with self.assertRaises(JobIntakeError):
                    fetch_job_posting('https://example.com/job')

    @patch('leads.services.job_intake.fetch_job_posting')
    def test_pasted_description_skips_fetch_and_preserves_text(self, mock_fetch):
        from .services.job_intake import analyze_job_intake

        analysis = analyze_job_intake(
            job_url='https://example.com/job',
            job_description='Senior Backend Engineer\nStripe\nRemote\n$150,000 - $180,000\nPython, Django, PostgreSQL',
        )

        mock_fetch.assert_not_called()
        self.assertEqual(analysis['source_type'], 'pasted')
        self.assertEqual(analysis['fields']['job_url'], 'https://example.com/job')
        self.assertIn('Python', analysis['fields']['job_description'])
        self.assertTrue(analysis['employer_research']['grounding_note'])
        self.assertEqual(analysis['fit_analysis'], {})


class JobIntakeViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='intakeuser', password='password123')
        self.client.force_login(self.user)

    def _analysis(self):
        return {
            'fields': {
                'company_name': 'Stripe',
                'role_title': 'Senior Backend Engineer',
                'job_url': 'https://example.com/job',
                'location': 'Remote',
                'salary': '$150,000 - $180,000',
                'employment_type': 'Full-time',
                'job_description': 'Build payment APIs with Python and Django.',
            },
            'warnings': [],
            'source_type': 'url',
            'employer_research': {
                'summary': 'Stripe is hiring a backend engineer.',
                'tech_stack': ['Python', 'Django'],
                'benefits': [],
                'work_arrangement': ['Remote'],
                'salary_transparency': True,
                'compensation_note': '$150,000 - $180,000',
                'red_flags': [],
                'unavailable': ['Company size'],
                'sources': ['https://example.com/job'],
                'grounding_note': 'Derived only from the posting.',
            },
            'fit_analysis': {},
            'extraction_status': 'extracted',
        }

    @patch('leads.views.analyze_job_intake')
    def test_preview_renders_without_creating_a_job(self, mock_analyze):
        mock_analyze.return_value = self._analysis()
        response = self.client.post(reverse('leads:intake-analyze'), {
            'job_url': 'https://example.com/job',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Senior Backend Engineer')
        self.assertContains(response, 'Employer Brief')
        self.assertEqual(JobApplication.objects.count(), 0)

    @patch('leads.views.analyze_job_intake')
    def test_preview_error_is_graceful(self, mock_analyze):
        from .services.job_intake import JobIntakeError

        mock_analyze.side_effect = JobIntakeError('Paste the description instead.')
        response = self.client.post(reverse('leads:intake-analyze'), {'job_url': 'http://127.0.0.1/'})

        self.assertEqual(response.status_code, 400)
        self.assertContains(response, 'Paste the description instead.', status_code=400)
        self.assertEqual(JobApplication.objects.count(), 0)

    def test_reanalysis_preserves_user_edits_and_status(self):
        job = JobApplication.objects.create(
            user=self.user,
            company_name='My Edited Company',
            role_title='Backend Engineer',
            status='interviewing',
            notes='Keep my notes',
            salary='',
            job_description='',
            job_url='https://example.com/job',
        )

        with patch('leads.views.analyze_job_intake', return_value=self._analysis()):
            response = self.client.post(reverse('leads:lead-reanalyze', args=[job.pk]), {
                'job_description': 'Build payment APIs with Python and Django.',
            })

        self.assertEqual(response.status_code, 200)
        job.refresh_from_db()
        self.assertEqual(job.status, 'interviewing')
        self.assertEqual(job.company_name, 'My Edited Company')
        self.assertEqual(job.notes, 'Keep my notes')
        self.assertEqual(job.salary, '$150,000 - $180,000')
        self.assertEqual(job.extraction_status, 'extracted')
        self.assertTrue(job.employer_research['summary'])
        self.assertIsNotNone(job.analyzed_at)

    def test_reanalysis_is_scoped_to_owner(self):
        other = User.objects.create_user(username='otherintake', password='password123')
        job = JobApplication.objects.create(user=other, company_name='Other', role_title='Dev')

        response = self.client.post(reverse('leads:lead-reanalyze', args=[job.pk]), {})

        self.assertEqual(response.status_code, 404)

    def test_lead_create_records_intake_provenance_and_grounded_research(self):
        response = self.client.post(reverse('leads:lead-create'), {
            'company_name': 'Stripe',
            'role_title': 'Senior Backend Engineer',
            'job_url': 'https://example.com/job',
            'intake_source': 'pasted',
            'status': 'saved',
            'job_description': 'Build payment APIs with Python and Django. Remote.',
        })

        self.assertEqual(response.status_code, 302)
        job = JobApplication.objects.get(user=self.user)
        self.assertEqual(job.intake_source, 'pasted')
        self.assertEqual(job.extraction_status, 'extracted')
        self.assertTrue(job.employer_research['grounding_note'])
        self.assertIsNotNone(job.analyzed_at)
