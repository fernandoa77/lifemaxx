from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class AuthenticationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("alex", password="a-secure-test-password")

    def test_dashboard_requires_authentication(self):
        response = self.client.get(reverse("dashboard:home"))

        self.assertRedirects(response, f"{reverse('login')}?next={reverse('dashboard:home')}")

    def test_user_can_log_in_and_log_out(self):
        response = self.client.post(reverse("login"), {"username": "alex", "password": "a-secure-test-password"})
        self.assertRedirects(response, reverse("dashboard:home"), fetch_redirect_response=False)

        response = self.client.post(reverse("logout"))
        self.assertRedirects(response, reverse("login"))
