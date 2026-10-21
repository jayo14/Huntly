from unittest import mock
from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.core import mail
from django.test import TestCase
from django.urls import reverse
from .forms import AppSettingForm
from .models import Lead, Message, AppSetting, AutomationRule, ScraperJob, RawLead
from .scraper_service import is_safe_url
from resumes.models import Payment


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
        # Create other user's lead, payment, message
        other_lead = Lead.objects.create(user=other_user, business_name="Other Biz", status='closed')
        Payment.objects.create(user=other_user, customer_name="Other Customer", amount=5000, method="cash")
        Message.objects.create(lead=other_lead, subject="Hi", body="Text")

        # Current user has nothing
        response = self.client.get(reverse('leads:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_leads'], 0)
        self.assertEqual(response.context['total_earnings'], 0)
        self.assertEqual(response.context['emails_sent_today'], 0)

    def test_dashboard_funnel_counts_and_percentages(self):
        Lead.objects.create(user=self.user, business_name="Biz 1", status='new', score=10)
        Lead.objects.create(user=self.user, business_name="Biz 2", status='new', score=20)
        Lead.objects.create(user=self.user, business_name="Biz 3", status='contacted', score=30)
        Lead.objects.create(user=self.user, business_name="Biz 4", status='closed', score=40)

        response = self.client.get(reverse('leads:dashboard'))
        self.assertEqual(response.status_code, 200)

        self.assertEqual(response.context['total_leads'], 4)
        self.assertEqual(response.context['conversion_rate'], 25.0)

        funnel_dict = {item['label']: (item['count'], item['percentage']) for item in response.context['funnel_stages']}
        self.assertEqual(funnel_dict['New'], (2, 50.0))
        self.assertEqual(funnel_dict['Contacted'], (1, 25.0))
        self.assertEqual(funnel_dict['Replied'], (0, 0))
        self.assertEqual(funnel_dict['Proposal Sent'], (0, 0))
        self.assertEqual(funnel_dict['Closed'], (1, 25.0))

    def test_dashboard_query_optimization(self):
        for i in range(10):
            status = Lead.STATUS_CHOICES[i % len(Lead.STATUS_CHOICES)][0]
            Lead.objects.create(user=self.user, business_name=f"Biz {i}", status=status, score=i * 10)

        with self.assertNumQueries(7):
            response = self.client.get(reverse('leads:dashboard'))
            self.assertEqual(response.status_code, 200)

class LeadTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='leaduser', password='password123')
        self.client.force_login(self.user)
        self.lead = Lead.objects.create(user=self.user, business_name="Test Biz", score=85)

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

    def test_lead_create_view_assigns_user(self):
        response = self.client.post(reverse('leads:lead-create'), {
            'business_name': 'New Created Biz',
            'score': 90,
            'status': 'new',
            'tone': 'professional'
        })
        self.assertEqual(response.status_code, 302)
        new_lead = Lead.objects.get(business_name='New Created Biz')
        self.assertEqual(new_lead.user, self.user)


class PipelineTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='pipeuser', password='password123')
        self.client.force_login(self.user)
        self.lead = Lead.objects.create(user=self.user, business_name="Pipeline Biz", status='new')

    def test_pipeline_view(self):
        response = self.client.get(reverse('leads:pipeline'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Pipeline Biz")


    def test_pipeline_view_unauthenticated(self):
        self.client.logout()
        response = self.client.get(reverse('leads:pipeline'))
        expected_url = f"{reverse(settings.LOGIN_URL)}?next={reverse('leads:pipeline')}"
        self.assertRedirects(response, expected_url)

    def test_pipeline_query_optimization(self):
        for i in range(15):
            status = Lead.STATUS_CHOICES[i % len(Lead.STATUS_CHOICES)][0]
            Lead.objects.create(user=self.user, business_name=f"Pipe Biz {i}", status=status, score=i)

        with self.assertNumQueries(3):
            response = self.client.get(reverse('leads:pipeline'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(len(response.context['stages']), len(Lead.STATUS_CHOICES))
            total_leads_in_stages = sum(stage['leads'].count() for stage in response.context['stages'])
            self.assertEqual(total_leads_in_stages, 16)  # 15 created here + 1 created in setUp


class LeadTenantIsolationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='user_a', password='password123')
        self.user_b = User.objects.create_user(username='user_b', password='password123')

        self.lead_a = Lead.objects.create(user=self.user_a, business_name="User A Biz", score=80, status='new')
        self.lead_b = Lead.objects.create(user=self.user_b, business_name="User B Biz", score=90, status='new')

    def test_user_a_cannot_see_user_b_leads_in_list(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('leads:lead-list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User A Biz")
        self.assertNotContains(response, "User B Biz")

    def test_user_a_cannot_see_user_b_leads_in_pipeline(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('leads:pipeline'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "User A Biz")
        self.assertNotContains(response, "User B Biz")

    def test_user_a_cannot_access_user_b_lead_detail(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('leads:lead-detail', args=[self.lead_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_user_a_cannot_update_user_b_lead(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse('leads:lead-update', args=[self.lead_b.pk]), {
            'business_name': 'Hacked Biz',
            'score': 100,
            'status': 'closed',
            'tone': 'professional'
        })
        self.assertEqual(response.status_code, 404)
        self.lead_b.refresh_from_db()
        self.assertEqual(self.lead_b.business_name, "User B Biz")

    def test_user_a_cannot_delete_user_b_lead(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse('leads:lead-delete', args=[self.lead_b.pk]))
        self.assertEqual(response.status_code, 404)
        self.assertTrue(Lead.objects.filter(pk=self.lead_b.pk).exists())

    def test_user_a_cannot_update_status_of_user_b_lead(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse('leads:update-status', args=[self.lead_b.pk]), {'status': 'closed'})
        self.assertEqual(response.status_code, 404)
        self.lead_b.refresh_from_db()
        self.assertEqual(self.lead_b.status, 'new')

    def test_user_a_cannot_send_or_generate_message_for_user_b_lead(self):
        self.client.force_login(self.user_a)
        res_gen = self.client.post(reverse('leads:generate-message', args=[self.lead_b.pk]))
        self.assertEqual(res_gen.status_code, 404)

        res_send = self.client.post(reverse('leads:send-message', args=[self.lead_b.pk]), {
            'subject': 'Spam',
            'body': 'Unauthorized'
        })
        self.assertEqual(res_send.status_code, 404)

class AppSettingTenantIsolationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='user_a', password='password123')
        self.user_b = User.objects.create_user(username='user_b', password='password123')
        self.setting_a = AppSetting.objects.create(user=self.user_a, email_address='user_a@test.com')
        self.setting_b = AppSetting.objects.create(user=self.user_b, email_address='user_b@test.com')

    def test_settings_are_isolated_per_user(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('leads:settings'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'user_a@test.com')
        self.assertNotContains(response, 'user_b@test.com')

    def test_toggle_setting_is_user_isolated(self):
        self.client.force_login(self.user_a)
        self.assertFalse(self.setting_a.auto_send_enabled)
        self.assertFalse(self.setting_b.auto_send_enabled)

        self.client.post(reverse('leads:toggle-setting'), {'field': 'auto_send_enabled'})
        self.setting_a.refresh_from_db()
        self.setting_b.refresh_from_db()
        self.assertTrue(self.setting_a.auto_send_enabled)
        self.assertFalse(self.setting_b.auto_send_enabled)

class AutomationRuleTenantIsolationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='user_a', password='password123')
        self.user_b = User.objects.create_user(username='user_b', password='password123')
        self.rule_a = AutomationRule.objects.create(user=self.user_a, name="Rule A", trigger_type="on_new")
        self.rule_b = AutomationRule.objects.create(user=self.user_b, name="Rule B", trigger_type="on_new")

    def test_rules_dashboard_isolation(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('leads:automation-dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertIn(self.rule_a, response.context['rules'])
        self.assertNotIn(self.rule_b, response.context['rules'])

        # Partial that renders the actual rule list
        partial_res = self.client.get(reverse('leads:rule-list-partial'))
        self.assertEqual(partial_res.status_code, 200)
        self.assertContains(partial_res, "Rule A")
        self.assertNotContains(partial_res, "Rule B")

    def test_rule_create_assigns_user(self):
        self.client.force_login(self.user_a)
        response = self.client.post(reverse('leads:rule-create'), {
            'name': 'New Rule A',
            'trigger_type': 'on_new',
            'delay_hours': 12,
            'is_active': True
        })
        self.assertEqual(response.status_code, 302)
        created_rule = AutomationRule.objects.get(name='New Rule A')
        self.assertEqual(created_rule.user, self.user_a)

    def test_user_a_cannot_mutate_user_b_rule(self):
        self.client.force_login(self.user_a)
        # Update
        res_update = self.client.post(reverse('leads:rule-update', args=[self.rule_b.pk]), {
            'name': 'Hacked Rule',
            'trigger_type': 'on_new',
            'delay_hours': 10
        })
        self.assertEqual(res_update.status_code, 404)

        # Toggle
        res_toggle = self.client.post(reverse('leads:toggle-rule', args=[self.rule_b.pk]))
        self.assertEqual(res_toggle.status_code, 404)

        # Delete
        res_delete = self.client.post(reverse('leads:rule-delete', args=[self.rule_b.pk]))
        self.assertEqual(res_delete.status_code, 404)
        self.assertTrue(AutomationRule.objects.filter(pk=self.rule_b.pk).exists())

class ScraperJobTenantIsolationTests(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(username='user_a', password='password123')
        self.user_b = User.objects.create_user(username='user_b', password='password123')
        self.job_a = ScraperJob.objects.create(user=self.user_a, name="Job A", niche="Niche A", keywords="k1", region="R1")
        self.job_b = ScraperJob.objects.create(user=self.user_b, name="Job B", niche="Niche B", keywords="k2", region="R2")
        self.raw_lead_b = RawLead.objects.create(job=self.job_b, business_name="Raw B", email="b@raw.com")

    def test_scraper_dashboard_isolation(self):
        self.client.force_login(self.user_a)
        response = self.client.get(reverse('leads:scraper-dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Job A")
        self.assertNotContains(response, "Job B")

    def test_user_a_cannot_access_or_mutate_user_b_job(self):
        self.client.force_login(self.user_a)
        # Detail
        self.assertEqual(self.client.get(reverse('leads:scraper-session-detail', args=[self.job_b.pk])).status_code, 404)
        # Terminate
        self.assertEqual(self.client.post(reverse('leads:scraper-terminate', args=[self.job_b.pk])).status_code, 404)
        # Logs
        self.assertEqual(self.client.get(reverse('leads:scraper-logs-partial', args=[self.job_b.pk])).status_code, 404)
        # Rename
        self.assertEqual(self.client.post(reverse('leads:scraper-job-rename', args=[self.job_b.pk]), {'name': 'Hacked'}).status_code, 404)

    def test_user_a_cannot_review_approve_or_delete_user_b_raw_leads(self):
        self.client.force_login(self.user_a)
        # Review
        self.assertEqual(self.client.get(reverse('leads:raw-lead-review', args=[self.raw_lead_b.pk])).status_code, 404)
        # Approve
        self.assertEqual(self.client.post(reverse('leads:raw-lead-approve', args=[self.raw_lead_b.pk])).status_code, 404)
        # Delete
        self.assertEqual(self.client.post(reverse('leads:raw-lead-delete', args=[self.raw_lead_b.pk])).status_code, 404)


class GenerateMessageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='xssuser', password='password123')
        self.client.force_login(self.user)

    def test_generate_message_xss_protection(self):
        xss_payload = "</script><script>alert('xss')</script>"
        lead = Lead.objects.create(
            user=self.user,
            business_name="Malicious Lead",
            problem=xss_payload,
            offer="<img src=x onerror=alert(1)>",
            score=50,
        )
        response = self.client.post(reverse('leads:generate-message', args=[lead.pk]))
        self.assertEqual(response.status_code, 200)

        # Ensure no unescaped executable script tags exist
        self.assertNotContains(response, "<script>")
        self.assertNotContains(response, "</script>")

        # Ensure payload is HTML entity escaped
        self.assertContains(response, "&lt;/script&gt;&lt;script&gt;alert(&#x27;xss&#x27;)&lt;/script&gt;")
        self.assertContains(response, "&lt;img src=x onerror=alert(1)&gt;")

        # Ensure out-of-band swap attributes are present
        self.assertContains(response, 'id="message-subject"')
        self.assertContains(response, 'id="message-body"')
        self.assertContains(response, 'hx-swap-oob="true"')


class AppSettingFormTests(TestCase):
    def test_password_widget_render_value_is_false(self):
        form = AppSettingForm()
        self.assertFalse(form.fields['email_password'].widget.render_value)

    def test_form_html_does_not_contain_stored_password(self):
        setting = AppSetting.objects.create(
            smtp_host='smtp.example.com',
            smtp_port=587,
            email_address='test@example.com',
            email_password='supersecretpassword'
        )
        form = AppSettingForm(instance=setting)
        html = form.as_p()
        self.assertNotIn('supersecretpassword', html)

    def test_form_clean_preserves_existing_password_when_blank(self):
        setting = AppSetting.objects.create(
            smtp_host='smtp.example.com',
            smtp_port=587,
            email_address='test@example.com',
            email_password='supersecretpassword'
        )
        data = {
            'smtp_host': 'smtp.updated.com',
            'smtp_port': 465,
            'email_address': 'updated@example.com',
            'email_password': '',  # left blank on update
            'daily_send_limit': 100,
            'default_tone': 'casual',
            'default_offer': 'New offer',
            'auto_send_enabled': False,
            'follow_ups_enabled': True,
        }
        form = AppSettingForm(data=data, instance=setting)
        self.assertTrue(form.is_valid(), form.errors)
        saved_setting = form.save()
        self.assertEqual(saved_setting.email_password, 'supersecretpassword')
        self.assertEqual(saved_setting.smtp_host, 'smtp.updated.com')

    def test_form_clean_updates_password_when_provided(self):
        setting = AppSetting.objects.create(
            smtp_host='smtp.example.com',
            smtp_port=587,
            email_address='test@example.com',
            email_password='supersecretpassword'
        )
        data = {
            'smtp_host': 'smtp.updated.com',
            'smtp_port': 465,
            'email_address': 'updated@example.com',
            'email_password': 'brandnewpassword',
            'daily_send_limit': 100,
            'default_tone': 'casual',
            'default_offer': 'New offer',
            'auto_send_enabled': False,
            'follow_ups_enabled': True,
        }
        form = AppSettingForm(data=data, instance=setting)
        self.assertTrue(form.is_valid(), form.errors)
        saved_setting = form.save()
        self.assertEqual(saved_setting.email_password, 'brandnewpassword')


class SendMessageTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="smtpuser", password="password123")
        self.client.force_login(self.user)
        self.lead = Lead.objects.create(
            user=self.user,
            business_name="Target Corp",
            email="contact@targetcorp.com",
            status="new",
            score=90
        )

    def test_send_message_unauthenticated(self):
        self.client.logout()
        url = reverse('leads:send-message', args=[self.lead.pk])
        response = self.client.post(url, {'subject': 'Subj', 'body': 'Text'})
        self.assertEqual(response.status_code, 302)

    def test_send_message_invalid_form(self):
        url = reverse('leads:send-message', args=[self.lead.pk])
        response = self.client.post(url, {'subject': ''})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.content.decode(), "Invalid form")

    def test_send_message_locmem_default_backend_success(self):
        url = reverse('leads:send-message', args=[self.lead.pk])
        response = self.client.post(url, {
            'subject': 'Partnership Opportunity',
            'body': 'We would love to collaborate with you.'
        })

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response.headers.get('HX-Trigger'), 'leadsChanged')

        # Verify email dispatched to mail.outbox
        self.assertEqual(len(mail.outbox), 1)
        sent_email = mail.outbox[0]
        self.assertEqual(sent_email.subject, 'Partnership Opportunity')
        self.assertEqual(sent_email.body, 'We would love to collaborate with you.')
        self.assertEqual(sent_email.to, ['contact@targetcorp.com'])
        self.assertEqual(sent_email.from_email, 'noreply@huntly.local')

        # Verify Lead state changed
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'contacted')
        self.assertIsNotNone(self.lead.last_contacted)

        # Verify Message record created
        msg = Message.objects.get(lead=self.lead)
        self.assertEqual(msg.subject, 'Partnership Opportunity')
        self.assertEqual(msg.body, 'We would love to collaborate with you.')

        # Verify success notification
        storage = get_messages(response.wsgi_request)
        message_texts = [m.message for m in storage]
        self.assertIn("Email sent to Target Corp!", message_texts)

    def test_send_message_smtp_configured_success(self):
        setting = AppSetting.objects.create(
            user=self.user,
            smtp_host='smtp.mailprovider.com',
            smtp_port=587,
            email_address='outreach@huntly.com',
            email_password='my_smtp_password'
        )

        url = reverse('leads:send-message', args=[self.lead.pk])
        with mock.patch('leads.views.get_connection') as mock_get_conn:
            mock_connection = mock.MagicMock()
            mock_get_conn.return_value = mock_connection

            with mock.patch('leads.views.EmailMessage.send', return_value=1) as mock_send:
                response = self.client.post(url, {
                    'subject': 'Custom SMTP Subject',
                    'body': 'Body via custom SMTP.'
                })

                self.assertEqual(response.status_code, 204)
                mock_get_conn.assert_called_once_with(
                    backend='django.core.mail.backends.smtp.EmailBackend',
                    host='smtp.mailprovider.com',
                    port=587,
                    username='outreach@huntly.com',
                    password='my_smtp_password',
                    use_tls=True
                )
                self.assertEqual(mock_send.call_count, 1)

        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'contacted')
        self.assertIsNotNone(self.lead.last_contacted)
        self.assertEqual(Message.objects.filter(lead=self.lead).count(), 1)

    def test_send_message_failure_does_not_advance_status(self):
        url = reverse('leads:send-message', args=[self.lead.pk])
        with mock.patch('leads.views.EmailMessage.send', side_effect=Exception("SMTP connection timed out")):
            response = self.client.post(url, {
                'subject': 'Failing Email',
                'body': 'This should fail.'
            })

            self.assertEqual(response.status_code, 500)
            self.assertIn("Failed to send email: SMTP connection timed out", response.content.decode())

        # Verify lead status was NOT advanced
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, 'new')
        self.assertIsNone(self.lead.last_contacted)

        # Verify no Message object created
        self.assertEqual(Message.objects.filter(lead=self.lead).count(), 0)

        # Verify error message was added
        storage = get_messages(response.wsgi_request)
        message_texts = [m.message for m in storage]
        self.assertIn("Failed to send email: SMTP connection timed out", message_texts)


class SafeUrlTests(TestCase):
    def test_unsafe_urls(self):
        unsafe_urls = [
            'http://127.0.0.1',
            'http://localhost',
            'http://169.254.169.254/latest/meta-data',
            'file:///etc/passwd',
        ]
        for url in unsafe_urls:
            with self.subTest(url=url):
                self.assertFalse(is_safe_url(url), f"Expected {url} to be unsafe")

    def test_safe_urls(self):
        safe_urls = [
            'http://example.com',
            'https://example.com',
        ]
        for url in safe_urls:
            with self.subTest(url=url):
                self.assertTrue(is_safe_url(url), f"Expected {url} to be safe")
