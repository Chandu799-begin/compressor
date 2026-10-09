"""Tests for the accounts application."""
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class AccountTests(TestCase):
    def test_profile_created_on_user_creation(self):
        user = User.objects.create_user(username="alice", password="Sup3rSecret!")
        self.assertTrue(hasattr(user, "profile"))
        self.assertEqual(user.profile.preferred_theme, "dark")

    def test_register_view(self):
        response = self.client.post(
            reverse("accounts:register"),
            {
                "username": "bob",
                "email": "bob@example.com",
                "password1": "Sup3rSecret!",
                "password2": "Sup3rSecret!",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(username="bob").exists())

    def test_login_view(self):
        User.objects.create_user(username="carol", password="Sup3rSecret!")
        response = self.client.post(
            reverse("accounts:login"),
            {"username": "carol", "password": "Sup3rSecret!"},
        )
        self.assertEqual(response.status_code, 302)

    def test_profile_requires_login(self):
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)
