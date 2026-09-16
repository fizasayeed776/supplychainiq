"""
Tests for apps/notifications/teams.py and apps/notifications/tasks.py.
"""
from unittest.mock import patch, MagicMock

from django.test import TestCase

from apps.core.models import Workspace, Vendor
from apps.notifications.teams import build_teams_card


# =============================================================================
# teams.py — build_teams_card
# =============================================================================

class BuildTeamsCardTests(TestCase):

    def test_basic_card_has_required_fields(self):
        card = build_teams_card("Alert Title", "Something happened")
        self.assertEqual(card["@type"], "MessageCard")
        self.assertEqual(card["title"], "Alert Title")
        self.assertEqual(card["text"], "Something happened")
        self.assertEqual(card["summary"], "Alert Title")
        self.assertNotIn("sections", card)

    def test_facts_are_included_as_section(self):
        card = build_teams_card("Title", "Body", facts={"Invoice": "INV-1", "Amount": 500})
        self.assertIn("sections", card)
        fact_names = [f["name"] for f in card["sections"][0]["facts"]]
        fact_values = [f["value"] for f in card["sections"][0]["facts"]]
        self.assertIn("Invoice", fact_names)
        self.assertIn("Amount", fact_names)
        # Values must be coerced to str
        self.assertIn("500", fact_values)
        self.assertIn("INV-1", fact_values)

    def test_facts_values_are_coerced_to_str(self):
        card = build_teams_card("T", "B", facts={"count": 42, "flag": True})
        values = {f["name"]: f["value"] for f in card["sections"][0]["facts"]}
        self.assertIsInstance(values["count"], str)
        self.assertIsInstance(values["flag"], str)

    def test_no_facts_produces_no_sections(self):
        card = build_teams_card("T", "B", facts=None)
        self.assertNotIn("sections", card)

    def test_empty_facts_dict_produces_no_sections(self):
        """Empty dict is falsy — same as None."""
        card = build_teams_card("T", "B", facts={})
        self.assertNotIn("sections", card)


# =============================================================================
# notifications/tasks.py — send_teams_alert
# =============================================================================

class SendTeamsAlertTests(TestCase):

    def setUp(self):
        self.workspace = Workspace.objects.create(name="Teams WS", slug="teams-ws")

    @patch("apps.workflow.outbound.post_signed_webhook")
    def test_teams_url_receives_card(self, mock_post):
        self.workspace.settings_json = {
            "outbound_webhook_urls": ["https://company.webhook.office.com/teams-hook"]
        }
        self.workspace.save()

        from apps.notifications.tasks import send_teams_alert
        send_teams_alert(str(self.workspace.id), "Discrepancy Alert", "INV-1 is discrepant")

        mock_post.assert_called_once()
        call_workspace, call_url, call_card = mock_post.call_args[0]
        self.assertEqual(call_workspace, self.workspace)
        self.assertIn("office.com", call_url)
        self.assertEqual(call_card["title"], "Discrepancy Alert")

    @patch("apps.workflow.outbound.post_signed_webhook")
    def test_non_teams_url_is_skipped(self, mock_post):
        """URLs that are not Teams / office.com must not be called."""
        self.workspace.settings_json = {
            "outbound_webhook_urls": ["https://generic-hook.example.com/post"]
        }
        self.workspace.save()

        from apps.notifications.tasks import send_teams_alert
        send_teams_alert(str(self.workspace.id), "Title", "Body")

        mock_post.assert_not_called()

    @patch("apps.workflow.outbound.post_signed_webhook")
    def test_multiple_urls_only_teams_ones_called(self, mock_post):
        self.workspace.settings_json = {
            "outbound_webhook_urls": [
                "https://company.webhook.office.com/hook1",
                "https://generic.example.com/hook",
                "https://teams.microsoft.com/hook2",
            ]
        }
        self.workspace.save()

        from apps.notifications.tasks import send_teams_alert
        send_teams_alert(str(self.workspace.id), "T", "B")

        self.assertEqual(mock_post.call_count, 2)

    @patch("apps.workflow.outbound.post_signed_webhook")
    def test_facts_forwarded_to_card(self, mock_post):
        self.workspace.settings_json = {
            "outbound_webhook_urls": ["https://company.webhook.office.com/hook"]
        }
        self.workspace.save()

        from apps.notifications.tasks import send_teams_alert
        send_teams_alert(
            str(self.workspace.id), "Title", "Body",
            facts={"Invoice": "INV-99", "Severity": "critical"},
        )

        _, _, card = mock_post.call_args[0]
        self.assertIn("sections", card)
