from django.contrib.auth.models import User
from django.test import TestCase, Client
from django.urls import reverse


class CoreViewTests(TestCase):
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
