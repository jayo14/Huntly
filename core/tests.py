from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse


class CoreViewTests(TestCase):
    def test_health_check_endpoint(self):
        response = self.client.get(reverse('core:health-check'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {'status': 'ok', 'app': 'huntly'})

    def test_landing_page_anonymous_user(self):
        response = self.client.get(reverse('core:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/landing.html')
        self.assertFalse(response.context['is_authenticated'])

    def test_landing_page_authenticated_user(self):
        user = User.objects.create_user(username='testuser', password='password123')
        self.client.force_login(user)
        response = self.client.get(reverse('core:landing'))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['is_authenticated'])

    def test_signup_view_get(self):
        response = self.client.get(reverse('core:signup'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/signup.html')

    def test_signup_view_valid_post(self):
        data = {
            'username': 'newuser',
            'password1': 'ComplexPass123!',
            'password2': 'ComplexPass123!',
        }
        response = self.client.post(reverse('core:signup'), data)
        self.assertRedirects(response, reverse('leads:dashboard'))
        self.assertTrue(User.objects.filter(username='newuser').exists())
        self.assertEqual(int(self.client.session['_auth_user_id']), User.objects.get(username='newuser').pk)

    def test_login_view_get(self):
        response = self.client.get(reverse('core:login'))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, 'core/login.html')

    def test_login_view_valid_post(self):
        user = User.objects.create_user(username='loginuser', password='ValidPassword123!')
        data = {
            'username': 'loginuser',
            'password': 'ValidPassword123!',
        }
        response = self.client.post(reverse('core:login'), data)
        self.assertRedirects(response, reverse('leads:dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)


class LogoutViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', password='password123')
        self.client = Client()

    def test_logout_get_returns_405_method_not_allowed(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.get(reverse('core:logout'))
        self.assertEqual(response.status_code, 405)
        self.assertTrue('_auth_user_id' in self.client.session)

    def test_logout_valid_post_logs_out_and_redirects(self):
        self.client.login(username='testuser', password='password123')
        response = self.client.post(reverse('core:logout'))
        self.assertRedirects(response, reverse('core:landing'))
        self.assertFalse('_auth_user_id' in self.client.session)

    def test_logout_post_csrf_protection(self):
        client = Client(enforce_csrf_checks=True)
        login_res = client.get(reverse('core:login'))
        csrf_token = login_res.cookies['csrftoken'].value

        client.login(username='testuser', password='password123')

        # POST without CSRF token should be rejected (403 Forbidden)
        response = client.post(reverse('core:logout'))
        self.assertEqual(response.status_code, 403)
        self.assertTrue('_auth_user_id' in client.session)

        # Valid POST with CSRF token should succeed and redirect
        response = client.post(reverse('core:logout'), {'csrfmiddlewaretoken': csrf_token})
        self.assertRedirects(response, reverse('core:landing'))
        self.assertFalse('_auth_user_id' in client.session)


class PostgreSQLConfigurationTests(TestCase):
    def test_postgres_url_scheme_parsing(self):
        import environ
        env = environ.Env()
        db_config = env.db_url_config('postgresql://huntly_user:secret_pass@ep-test.neon.tech:5432/huntly?sslmode=require')
        self.assertEqual(db_config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(db_config['NAME'], 'huntly')
        self.assertEqual(db_config['USER'], 'huntly_user')
        self.assertEqual(db_config['PASSWORD'], 'secret_pass')
        self.assertEqual(db_config['HOST'], 'ep-test.neon.tech')
        self.assertEqual(db_config['PORT'], 5432)
        self.assertEqual(db_config['OPTIONS'], {'sslmode': 'require'})

    def test_legacy_postgres_url_scheme_parsing(self):
        import environ
        env = environ.Env()
        db_config = env.db_url_config('postgres://huntly_user:secret_pass@localhost:5432/huntly_db')
        self.assertEqual(db_config['ENGINE'], 'django.db.backends.postgresql')
        self.assertEqual(db_config['NAME'], 'huntly_db')


class FirstSessionJourneyE2ETests(TestCase):
    """
    End-to-end verification of a candidate's complete first session journey:
    1. Sign up.
    2. Review empty state & build Master Profile.
    3. Profile completion assessment.
    4. Track target job posting with description.
    5. Run evidence-grounded tailoring.
    6. Review documents and fit heuristic.
    7. Export ATS resume.
    8. View pipeline Kanban and follow-up next actions.
    """
    def test_first_session_complete_journey(self):
        # Step 1: User signs up
        signup_data = {
            'username': 'firstseeker',
            'password1': 'StrongSeekerPass123!',
            'password2': 'StrongSeekerPass123!',
        }
        res_signup = self.client.post(reverse('core:signup'), signup_data)
        self.assertRedirects(res_signup, reverse('leads:dashboard'))
        user = User.objects.get(username='firstseeker')

        # Step 2: Dashboard displays Step 1 onboarding next action
        res_dash_1 = self.client.get(reverse('leads:dashboard'))
        self.assertEqual(res_dash_1.status_code, 200)
        self.assertContains(res_dash_1, "Complete Your Master Career Profile")
        self.assertEqual(res_dash_1.context['next_action']['step'], 1)

        # Step 3: User creates Master Career Profile
        from resumes.models import Resume, ApplicationDocument
        from leads.models import JobApplication

        resume = Resume.objects.create(
            user=user,
            full_name='Jordan Reed',
            email='jordan.reed@example.com',
            phone='555-0199',
            location='Austin, TX',
            tagline='Senior Distributed Systems Engineer',
            summary='Senior engineer with 8+ years designing scalable real-time architectures and backend microservices.',
            technical_skills=[
                {'name': 'Python', 'proficiency': 'Expert'},
                {'name': 'PostgreSQL', 'proficiency': 'Advanced'},
                {'name': 'Docker', 'proficiency': 'Advanced'},
                {'name': 'Redis', 'proficiency': 'Advanced'}
            ],
            experiences=[{
                'role': 'Backend Lead',
                'company': 'TechFlow Inc',
                'dates': '2021 - Present',
                'responsibilities': ['Led backend engineering team of 6.'],
                'accomplishments': [
                    'Reduced API latency by 45% through Redis caching and query indexing.',
                    'Engineered resilient webhook pipeline handling 5M daily events.'
                ]
            }],
            education=[{
                'degree': 'B.S. in Computer Science',
                'institution': 'University of Texas',
                'dates': '2013 - 2017'
            }]
        )

        assessment = resume.get_completion_assessment()
        self.assertGreaterEqual(assessment['score'], 80)
        self.assertTrue(assessment['is_complete'])

        # Step 4: User tracks first target job
        job = JobApplication.objects.create(
            user=user,
            company_name='ScaleCloud',
            role_title='Senior Backend Engineer',
            location='Remote, US',
            salary='$170,000 - $195,000',
            contact_name='David Kim',
            contact_email='david.kim@scalecloud.io',
            job_description='We are looking for a Senior Backend Engineer proficient in Python, PostgreSQL, and distributed systems to optimize our streaming data platform.',
            status='saved'
        )

        # Step 5: Dashboard now updates Next Action to Tailor Application (Step 3)
        res_dash_2 = self.client.get(reverse('leads:dashboard'))
        self.assertEqual(res_dash_2.context['next_action']['step'], 3)
        self.assertIn('Tailor Application', res_dash_2.context['next_action']['title'])

        # Step 6: User runs AI Tailoring
        res_tailor = self.client.post(reverse('leads:generate-message', args=[job.pk]))
        self.assertEqual(res_tailor.status_code, 200)

        job.refresh_from_db()
        self.assertTrue(bool(job.tailored_resume_text))
        self.assertTrue(bool(job.cover_letter))
        self.assertGreaterEqual(job.score, 50)
        self.assertTrue(ApplicationDocument.objects.filter(job_application=job).exists())

        # Step 7: User downloads tailored ATS DOCX resume
        res_download = self.client.get(f"{reverse('resumes:resume-download', args=[resume.pk])}?job_id={job.pk}&format=docx")
        self.assertEqual(res_download.status_code, 200)
        self.assertEqual(res_download['Content-Type'], 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')

        # Step 8: View pipeline Kanban and follow-up
        res_pipeline = self.client.get(reverse('leads:pipeline'))
        self.assertEqual(res_pipeline.status_code, 200)
        self.assertContains(res_pipeline, "ScaleCloud")
