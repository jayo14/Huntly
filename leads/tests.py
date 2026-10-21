from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from .models import Lead, Message, AppSetting, AutomationRule, ScraperJob, RawLead
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
