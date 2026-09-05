"""
Registration endpoint tests.
Covers: success, duplicate email, weak password, missing fields, workspace creation.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient

from .models import Workspace, WorkspaceMembership

User = get_user_model()

ENDPOINT = "/api/auth/register/"


class RegistrationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def _post(self, payload):
        return self.client.post(ENDPOINT, payload, format="json")

    # ── Happy path ────────────────────────────────────────────────────────────

    def test_successful_registration_returns_201_and_tokens(self):
        r = self._post({
            "email": "alice@acme.com",
            "password": "Str0ng!Pass#99",
            "full_name": "Alice Nguyen",
            "workspace_name": "Acme Procurement",
        })
        self.assertEqual(r.status_code, 201)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)
        self.assertTrue(len(r.data["access"]) > 20)
        self.assertTrue(len(r.data["refresh"]) > 20)

    def test_user_is_created_with_correct_fields(self):
        self._post({
            "email": "bob@beta.io",
            "password": "Str0ng!Pass#99",
            "full_name": "Bob Smith",
            "workspace_name": "Beta Corp",
        })
        user = User.objects.get(email="bob@beta.io")
        self.assertEqual(user.username, "bob@beta.io")
        self.assertEqual(user.first_name, "Bob")
        self.assertEqual(user.last_name, "Smith")

    def test_workspace_and_owner_membership_are_created(self):
        r = self._post({
            "email": "carol@delta.com",
            "password": "Str0ng!Pass#99",
            "full_name": "Carol Jones",
            "workspace_name": "Delta Supplies",
        })
        ws_id = r.data["workspace"]["id"]
        workspace = Workspace.objects.get(id=ws_id)
        self.assertEqual(workspace.name, "Delta Supplies")
        user = User.objects.get(email="carol@delta.com")
        membership = WorkspaceMembership.objects.get(workspace=workspace, user=user)
        self.assertEqual(membership.role, "owner")

    def test_response_contains_workspace_name_and_slug(self):
        r = self._post({
            "email": "dan@echo.com",
            "password": "Str0ng!Pass#99",
            "full_name": "Dan Park",
            "workspace_name": "Echo Logistics",
        })
        self.assertEqual(r.data["workspace"]["name"], "Echo Logistics")
        self.assertEqual(r.data["workspace"]["slug"], "echo-logistics")

    def test_workspace_name_defaults_when_omitted(self):
        r = self._post({
            "email": "eve@foxtrot.com",
            "password": "Str0ng!Pass#99",
            "full_name": "Eve Chen",
        })
        self.assertEqual(r.status_code, 201)
        # Default: "<FirstName>'s Workspace"
        self.assertIn("Eve", r.data["workspace"]["name"])

    # ── Duplicate email ───────────────────────────────────────────────────────

    def test_duplicate_email_returns_400_not_500(self):
        payload = {
            "email": "dup@test.com",
            "password": "Str0ng!Pass#99",
            "full_name": "Dup User",
            "workspace_name": "Dup Corp",
        }
        r1 = self._post(payload)
        r2 = self._post({**payload, "workspace_name": "Dup Corp 2"})
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 400)
        self.assertIn("email", r2.data)
        self.assertIn("already registered", str(r2.data["email"]))

    def test_duplicate_email_case_insensitive(self):
        self._post({
            "email": "UPPER@test.com",
            "password": "Str0ng!Pass#99",
            "full_name": "Upper User",
            "workspace_name": "Upper Corp",
        })
        r2 = self._post({
            "email": "upper@test.com",
            "password": "Str0ng!Pass#99",
            "full_name": "Lower User",
            "workspace_name": "Lower Corp",
        })
        self.assertEqual(r2.status_code, 400)

    # ── Password validation ───────────────────────────────────────────────────

    def test_short_password_returns_400(self):
        r = self._post({
            "email": "short@pw.com",
            "password": "abc",
            "full_name": "Short Pw",
            "workspace_name": "Short Corp",
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.data)

    def test_numeric_only_password_rejected(self):
        r = self._post({
            "email": "numeric@pw.com",
            "password": "12345678",
            "full_name": "Numeric Pw",
            "workspace_name": "Num Corp",
        })
        self.assertEqual(r.status_code, 400)
        self.assertIn("password", r.data)

    # ── Missing required fields ───────────────────────────────────────────────

    def test_missing_email_returns_400(self):
        r = self._post({"password": "Str0ng!Pass#99", "full_name": "No Email"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("email", r.data)

    def test_missing_full_name_returns_400(self):
        r = self._post({"email": "no@name.com", "password": "Str0ng!Pass#99"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("full_name", r.data)

    # ── Slug uniqueness ───────────────────────────────────────────────────────

    def test_slug_collision_resolves_without_error(self):
        """Two signups with the same workspace_name must both succeed."""
        r1 = self._post({
            "email": "a@slug.com", "password": "Str0ng!Pass#99",
            "full_name": "A Person", "workspace_name": "Same Name Corp",
        })
        r2 = self._post({
            "email": "b@slug.com", "password": "Str0ng!Pass#99",
            "full_name": "B Person", "workspace_name": "Same Name Corp",
        })
        self.assertEqual(r1.status_code, 201)
        self.assertEqual(r2.status_code, 201)
        self.assertNotEqual(r1.data["workspace"]["slug"], r2.data["workspace"]["slug"])

    # ── Tokens are immediately usable ─────────────────────────────────────────

    def test_returned_access_token_authenticates_workspace_api(self):
        r = self._post({
            "email": "token@test.com",
            "password": "Str0ng!Pass#99",
            "full_name": "Token Tester",
            "workspace_name": "Token Corp",
        })
        access = r.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        ws_r = self.client.get("/api/core/workspaces/")
        self.assertEqual(ws_r.status_code, 200)
        names = [w["name"] for w in (ws_r.data.get("results") or ws_r.data)]
        self.assertIn("Token Corp", names)
