from django.contrib.auth.models import User
from django.test import TestCase
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

    def test_logout_view_redirects_to_landing(self):
        user = User.objects.create_user(username='logoutuser', password='ValidPassword123!')
        self.client.force_login(user)
        response = self.client.get(reverse('core:logout'))
        self.assertRedirects(response, reverse('core:landing'))
        self.assertNotIn('_auth_user_id', self.client.session)
