"""Tests of the profile page: e-mail, home address and password sections."""

from core.tests.helpers import HtmxClientMixin
from django.test import TestCase
from django.urls import reverse

from accounts.tests.factories import UserFactory


class ProfileAccessTests(HtmxClientMixin, TestCase):
    """Access to the profile page and its fragments."""

    def test_page_renders_for_logged_in_user(self):
        """The profile page shows the three sections to a logged-in user."""
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)
        for text in ("Adresse e-mail", "Adresse du domicile", "Mot de passe"):
            self.assertContains(response, text)

    def test_anonymous_page_redirects_to_login(self):
        """An anonymous visitor is redirected to the login page."""
        self.client.logout()
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 302)

    def test_anonymous_htmx_gets_401_with_redirect(self):
        """An anonymous HTMX request gets 401 and an ``HX-Redirect`` header."""
        self.client.logout()
        for name in ("profile_email", "profile_address", "profile_password"):
            response = self.htmx_post(reverse(f"accounts:{name}"))
            self.assertEqual(response.status_code, 401)
            self.assertIn("HX-Redirect", response)


class ProfileEmailTests(HtmxClientMixin, TestCase):
    """The e-mail section."""

    def test_edit_mode_shows_form(self):
        """``?edit=1`` renders the form."""
        response = self.htmx_get(reverse("accounts:profile_email"), {"edit": 1})
        self.assertContains(response, "<form")

    def test_valid_post_saves_email(self):
        """A valid e-mail is saved and the read view is rendered."""
        response = self.htmx_post(
            reverse("accounts:profile_email"), {"email": "new@example.com"}
        )
        self.assertEqual(response.status_code, 200)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, "new@example.com")

    def test_invalid_post_returns_422(self):
        """An invalid e-mail returns 422 and changes nothing."""
        before = self.owner.email
        response = self.htmx_post(reverse("accounts:profile_email"), {"email": "nope"})
        self.assertEqual(response.status_code, 422)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.email, before)

    def test_only_current_user_is_changed(self):
        """Saving the e-mail leaves other users untouched."""
        before = self.other.email
        self.htmx_post(reverse("accounts:profile_email"), {"email": "new@example.com"})
        self.other.refresh_from_db()
        self.assertEqual(self.other.email, before)


class ProfileAddressTests(HtmxClientMixin, TestCase):
    """The home address section."""

    def test_valid_post_saves_address(self):
        """A complete address is saved."""
        response = self.htmx_post(
            reverse("accounts:profile_address"),
            {
                "address_line": "12 rue des Lilas",
                "postal_code": "69003",
                "city": "Lyon",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.owner.refresh_from_db()
        self.assertEqual(self.owner.city, "Lyon")
        self.assertContains(response, "12 rue des Lilas")

    def test_missing_city_returns_422(self):
        """A missing mandatory field returns 422."""
        response = self.htmx_post(
            reverse("accounts:profile_address"),
            {"address_line": "12 rue des Lilas", "postal_code": "69003"},
        )
        self.assertEqual(response.status_code, 422)


class ProfilePasswordTests(HtmxClientMixin, TestCase):
    """The password section."""

    def post(self, **overrides):
        """Post a password change, with ``overrides`` on a valid payload."""
        data = {
            "old_password": "password",
            "new_password1": "Sup3r-secret-phrase",
            "new_password2": "Sup3r-secret-phrase",
        } | overrides
        return self.htmx_post(reverse("accounts:profile_password"), data)

    def test_valid_change_updates_password_and_date(self):
        """A valid change sets the new password and ``password_changed_at``."""
        response = self.post()
        self.assertEqual(response.status_code, 200)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("Sup3r-secret-phrase"))
        self.assertIsNotNone(self.owner.password_changed_at)

    def test_session_stays_open_after_change(self):
        """The user is still logged in after changing the password."""
        self.post()
        response = self.client.get(reverse("accounts:profile"))
        self.assertEqual(response.status_code, 200)

    def test_wrong_old_password_returns_422(self):
        """A wrong current password returns 422 and keeps the old password."""
        response = self.post(old_password="wrong")
        self.assertEqual(response.status_code, 422)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("password"))

    def test_weak_password_returns_422(self):
        """A numeric-only password is refused by the validators."""
        response = self.post(new_password1="12345678", new_password2="12345678")
        self.assertEqual(response.status_code, 422)

    def test_get_is_not_allowed(self):
        """The password endpoint only accepts POST."""
        response = self.htmx_get(reverse("accounts:profile_password"))
        self.assertEqual(response.status_code, 405)


class ProfileNavigationTests(TestCase):
    """The navigation bar links to the profile."""

    def test_nav_links_to_profile(self):
        """The layout shows a link to the profile page."""
        user = UserFactory()
        self.client.force_login(user)
        response = self.client.get(reverse("core:dashboard"))
        self.assertContains(response, reverse("accounts:profile"))
