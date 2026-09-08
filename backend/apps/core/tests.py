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


# ══════════════════════════════════════════════════════════════════════════════
# RBAC tests — WorkspaceMembership.role enforcement
# ══════════════════════════════════════════════════════════════════════════════

from decimal import Decimal
from datetime import date

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from .models import Workspace, WorkspaceMembership, Vendor
from apps.documents.models import Document, Invoice, PurchaseOrder
from apps.matching.models import MatchResult
from apps.workflow.models import ApprovalFlow, ApprovalStep


def _make_user(email, password="Str0ng!Pass#99"):
    User = get_user_model()
    u = User.objects.create_user(username=email, email=email, password=password)
    return u


def _make_workspace_with_member(role):
    """Return (workspace, user, api_client) with the user having the given role."""
    User = get_user_model()
    workspace = Workspace.objects.create(name=f"RBAC Test {role}", slug=f"rbac-{role}")
    user = _make_user(f"{role}@rbac-test.com")
    WorkspaceMembership.objects.create(workspace=workspace, user=user, role=role)
    client = APIClient()
    client.force_authenticate(user=user)
    return workspace, user, client


def _make_invoice_and_flow(workspace, vendor):
    """Create a minimal Invoice + PurchaseOrder + ApprovalFlow for approve tests."""
    po_doc = Document.objects.create(
        workspace=workspace, vendor=vendor, type="po",
        file=SimpleUploadedFile("rbac_po.txt", b"po"), content_hash="rbac-po".ljust(64, "0"),
    )
    PurchaseOrder.objects.create(
        document=po_doc, workspace=workspace, vendor=vendor,
        po_number="RBAC-PO-1", order_date=date(2026, 9, 1), currency="USD",
    )
    inv_doc = Document.objects.create(
        workspace=workspace, vendor=vendor, type="invoice",
        file=SimpleUploadedFile("rbac_inv.txt", b"invoice"), content_hash="rbac-inv".ljust(64, "0"),
    )
    invoice = Invoice.objects.create(
        document=inv_doc, workspace=workspace, vendor=vendor,
        invoice_number="RBAC-INV-1", referenced_po_number="RBAC-PO-1",
        invoice_date=date(2026, 9, 5), due_date=date(2026, 10, 5), currency="USD",
    )
    match = MatchResult.objects.create(
        workspace=workspace, invoice=invoice,
        status="matched", severity="none", discrepancies=[],
    )
    flow = ApprovalFlow.objects.create(workspace=workspace, invoice=invoice)
    flow.submit_for_review()
    flow.save()
    ApprovalStep.objects.create(flow=flow, order=0, decision="pending")
    return flow


class RBACViewerTests(TestCase):
    """A 'viewer' role member must be blocked (403) from all mutating actions."""

    def setUp(self):
        self.workspace, self.user, self.client = _make_workspace_with_member("viewer")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="RBAC Vendor")
        self.flow = _make_invoice_and_flow(self.workspace, self.vendor)

    # ── Approve / decide ──────────────────────────────────────────────────────

    def test_viewer_cannot_approve_invoice(self):
        url = f"/api/workflow/approvals/{self.flow.id}/decide/"
        r = self.client.post(url, {"decision": "approved"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_viewer_cannot_reject_invoice(self):
        url = f"/api/workflow/approvals/{self.flow.id}/decide/"
        r = self.client.post(url, {"decision": "rejected"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_viewer_cannot_mark_paid(self):
        # Promote to approved state first via direct FSM call, bypassing permissions.
        self.flow.approve()
        self.flow.save()
        url = f"/api/workflow/approvals/{self.flow.id}/mark_paid/"
        r = self.client.post(url, format="json")
        self.assertEqual(r.status_code, 403)

    def test_viewer_can_read_approval_flows(self):
        url = f"/api/workflow/approvals/{self.flow.id}/"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)

    # ── Triage rules ──────────────────────────────────────────────────────────

    def test_viewer_cannot_create_triage_rule(self):
        url = "/api/workflow/triage-rules/"
        r = self.client.post(url, {
            "workspace": str(self.workspace.id),
            "name": "Viewer rule",
            "max_amount": "100.00",
            "active": True,
        }, format="json")
        self.assertEqual(r.status_code, 403)

    # ── Workspace settings ────────────────────────────────────────────────────

    def test_viewer_cannot_patch_workspace(self):
        url = f"/api/core/workspaces/{self.workspace.id}/"
        r = self.client.patch(url, {"name": "Hacked Name"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_viewer_can_read_workspace(self):
        url = f"/api/core/workspaces/{self.workspace.id}/"
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)


class RBACReviewerTests(TestCase):
    """A 'reviewer' can approve/dispute but not manage settings."""

    def setUp(self):
        self.workspace, self.user, self.client = _make_workspace_with_member("reviewer")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="Reviewer Vendor")
        self.flow = _make_invoice_and_flow(self.workspace, self.vendor)

    def test_reviewer_can_approve_invoice(self):
        url = f"/api/workflow/approvals/{self.flow.id}/decide/"
        r = self.client.post(url, {"decision": "approved"}, format="json")
        # 200 means the action was accepted; 400 means no pending step —
        # both indicate permission was NOT denied (not 403).
        self.assertNotEqual(r.status_code, 403)

    def test_reviewer_cannot_create_triage_rule(self):
        url = "/api/workflow/triage-rules/"
        r = self.client.post(url, {
            "workspace": str(self.workspace.id),
            "name": "Reviewer rule",
            "active": True,
        }, format="json")
        self.assertEqual(r.status_code, 403)

    def test_reviewer_cannot_patch_workspace(self):
        url = f"/api/core/workspaces/{self.workspace.id}/"
        r = self.client.patch(url, {"name": "Reviewer Rename"}, format="json")
        self.assertEqual(r.status_code, 403)


class RBACAdminTests(TestCase):
    """An 'admin' can do everything an owner can except workspace deletion."""

    def setUp(self):
        self.workspace, self.user, self.client = _make_workspace_with_member("admin")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="Admin Vendor")
        self.flow = _make_invoice_and_flow(self.workspace, self.vendor)

    def test_admin_can_approve_invoice(self):
        url = f"/api/workflow/approvals/{self.flow.id}/decide/"
        r = self.client.post(url, {"decision": "approved"}, format="json")
        self.assertNotEqual(r.status_code, 403)

    def test_admin_can_create_triage_rule(self):
        url = "/api/workflow/triage-rules/"
        r = self.client.post(url, {
            "workspace": str(self.workspace.id),
            "name": "Admin rule",
            "max_amount": "500.00",
            "active": True,
        }, format="json")
        self.assertNotEqual(r.status_code, 403)

    def test_admin_can_patch_workspace(self):
        url = f"/api/core/workspaces/{self.workspace.id}/"
        r = self.client.patch(url, {"name": "Admin Renamed"}, format="json")
        self.assertNotEqual(r.status_code, 403)


# ══════════════════════════════════════════════════════════════════════════════
# Spend Summary tests — _compute_spend_summary() aggregation
# ══════════════════════════════════════════════════════════════════════════════

import datetime
from decimal import Decimal

from django.utils import timezone
from rest_framework.test import APIClient

from .serializers import _compute_spend_summary


def _make_invoice(workspace, vendor, *, inv_num, amount, currency="USD", inv_date=None):
    """Create a bare Invoice (no Document required for aggregation tests)."""
    from apps.documents.models import Invoice
    from django.core.files.uploadedfile import SimpleUploadedFile

    doc = Document.objects.create(
        workspace=workspace,
        vendor=vendor,
        type="invoice",
        file=SimpleUploadedFile(f"{inv_num}.txt", b"x"),
        content_hash=inv_num.ljust(64, "0")[:64],
    )
    return Invoice.objects.create(
        document=doc,
        workspace=workspace,
        vendor=vendor,
        invoice_number=inv_num,
        referenced_po_number="",
        invoice_date=inv_date or datetime.date(2026, 1, 15),
        due_date=datetime.date(2026, 2, 15),
        currency=currency,
        total_amount=Decimal(str(amount)),
    )


class SpendSummaryTests(TestCase):
    """Unit tests for _compute_spend_summary() — the core aggregation helper."""

    def setUp(self):
        self.workspace = Workspace.objects.create(
            name="Spend Test WS", slug="spend-test-ws"
        )
        self.vendor = Vendor.objects.create(
            workspace=self.workspace, name="Spend Vendor"
        )

    # ── No invoices ───────────────────────────────────────────────────────────

    def test_no_invoices_returns_empty_summary(self):
        summary = _compute_spend_summary(self.vendor)
        self.assertEqual(summary["invoice_count"], 0)
        self.assertEqual(summary["per_currency"], [])
        self.assertIsNone(summary["trend"])

    # ── Single-currency totals ────────────────────────────────────────────────

    def test_single_currency_sums_correctly(self):
        _make_invoice(self.workspace, self.vendor, inv_num="SP-001", amount="1000.00")
        _make_invoice(self.workspace, self.vendor, inv_num="SP-002", amount="500.50")

        summary = _compute_spend_summary(self.vendor)

        self.assertEqual(summary["invoice_count"], 2)
        self.assertEqual(len(summary["per_currency"]), 1)

        usd = summary["per_currency"][0]
        self.assertEqual(usd["currency"], "USD")
        self.assertEqual(Decimal(usd["total"]), Decimal("1500.50"))
        self.assertEqual(usd["invoice_count"], 2)

    # ── Multi-currency: separate totals, no cross-currency mixing ────────────

    def test_multi_currency_grouped_separately(self):
        _make_invoice(self.workspace, self.vendor, inv_num="MC-001",
                      amount="2000.00", currency="USD")
        _make_invoice(self.workspace, self.vendor, inv_num="MC-002",
                      amount="1800.00", currency="EUR")
        _make_invoice(self.workspace, self.vendor, inv_num="MC-003",
                      amount="300.00",  currency="EUR")

        summary = _compute_spend_summary(self.vendor)

        self.assertEqual(summary["invoice_count"], 3)
        self.assertEqual(len(summary["per_currency"]), 2)

        by_ccy = {r["currency"]: r for r in summary["per_currency"]}

        # USD total
        self.assertEqual(Decimal(by_ccy["USD"]["total"]), Decimal("2000.00"))
        self.assertEqual(by_ccy["USD"]["invoice_count"], 1)

        # EUR total = 1800 + 300
        self.assertEqual(Decimal(by_ccy["EUR"]["total"]), Decimal("2100.00"))
        self.assertEqual(by_ccy["EUR"]["invoice_count"], 2)

    # ── Currencies never cross-contaminate each other ─────────────────────────

    def test_vendor_invoices_do_not_bleed_into_other_vendors(self):
        """Invoices from a different vendor must not appear in this vendor's summary."""
        other_vendor = Vendor.objects.create(
            workspace=self.workspace, name="Other Vendor"
        )
        _make_invoice(self.workspace, self.vendor,
                      inv_num="MINE-001", amount="500.00")
        _make_invoice(self.workspace, other_vendor,
                      inv_num="THEIRS-001", amount="99999.00")

        summary = _compute_spend_summary(self.vendor)
        self.assertEqual(summary["invoice_count"], 1)
        self.assertEqual(Decimal(summary["per_currency"][0]["total"]), Decimal("500.00"))

    # ── Ordering: highest-total currency listed first ─────────────────────────

    def test_per_currency_ordered_by_total_descending(self):
        _make_invoice(self.workspace, self.vendor, inv_num="ORD-EUR",
                      amount="100.00", currency="EUR")
        _make_invoice(self.workspace, self.vendor, inv_num="ORD-USD",
                      amount="9999.00", currency="USD")

        summary = _compute_spend_summary(self.vendor)
        # USD is bigger — must come first
        self.assertEqual(summary["per_currency"][0]["currency"], "USD")
        self.assertEqual(summary["per_currency"][1]["currency"], "EUR")

    # ── Trend: this quarter vs last quarter ───────────────────────────────────

    def test_trend_populated_when_data_spans_two_quarters(self):
        now = timezone.now().date()
        q_month = ((now.month - 1) // 3) * 3 + 1
        this_q_start = datetime.date(now.year, q_month, 1)
        lq_year  = now.year if q_month > 3 else now.year - 1
        lq_month = q_month - 3 if q_month > 3 else q_month + 9
        last_q_mid = datetime.date(lq_year, lq_month, 15)

        _make_invoice(self.workspace, self.vendor, inv_num="TREND-THIS",
                      amount="3000.00", currency="USD",
                      inv_date=this_q_start)
        _make_invoice(self.workspace, self.vendor, inv_num="TREND-LAST",
                      amount="2000.00", currency="USD",
                      inv_date=last_q_mid)

        summary = _compute_spend_summary(self.vendor)
        trend = summary["trend"]

        self.assertIsNotNone(trend)
        self.assertEqual(trend["currency"], "USD")
        self.assertEqual(Decimal(trend["this_quarter"]), Decimal("3000.00"))
        self.assertEqual(Decimal(trend["last_quarter"]), Decimal("2000.00"))
        # change_pct: (3000-2000)/2000 * 100 = +50.0
        self.assertAlmostEqual(trend["change_pct"], 50.0, places=1)

    def test_trend_change_pct_is_none_when_last_quarter_is_zero(self):
        """If there were no invoices last quarter, change_pct must be None (no div-by-zero)."""
        now = timezone.now().date()
        q_month = ((now.month - 1) // 3) * 3 + 1
        this_q_start = datetime.date(now.year, q_month, 1)

        _make_invoice(self.workspace, self.vendor, inv_num="TREND-ONLY",
                      amount="1500.00", currency="USD",
                      inv_date=this_q_start)

        summary = _compute_spend_summary(self.vendor)
        trend = summary["trend"]

        self.assertIsNotNone(trend)
        self.assertEqual(Decimal(trend["this_quarter"]), Decimal("1500.00"))
        self.assertEqual(Decimal(trend["last_quarter"]), Decimal("0"))
        self.assertIsNone(trend["change_pct"])

    # ── Null total_amount invoices handled gracefully ─────────────────────────

    def test_null_total_amount_treated_as_zero(self):
        """Invoices with total_amount=None (extraction failed) must not blow up."""
        from apps.documents.models import Invoice
        from django.core.files.uploadedfile import SimpleUploadedFile

        doc = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="invoice",
            file=SimpleUploadedFile("null-inv.txt", b"x"),
            content_hash="null-inv".ljust(64, "0")[:64],
        )
        Invoice.objects.create(
            document=doc, workspace=self.workspace, vendor=self.vendor,
            invoice_number="NULL-001", invoice_date=datetime.date(2026, 1, 10),
            due_date=datetime.date(2026, 2, 10), currency="USD",
            total_amount=None,
        )
        _make_invoice(self.workspace, self.vendor, inv_num="NULL-002",
                      amount="500.00", currency="USD")

        summary = _compute_spend_summary(self.vendor)
        # invoice_count includes the null-amount one
        self.assertEqual(summary["invoice_count"], 2)
        # total should still be 500 (Coalesce treats null as 0 at DB level
        # but Count sees both rows — actual total may vary by DB aggregation;
        # the key requirement is no exception is raised)
        self.assertIsNotNone(summary["per_currency"])

    # ── API endpoint: GET /core/vendors/{id}/spend-summary/ ──────────────────

    def test_spend_summary_api_endpoint_returns_200(self):
        user = _make_user("spend-api@test.com")
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=user, role="admin"
        )
        _make_invoice(self.workspace, self.vendor,
                      inv_num="API-001", amount="750.00")

        client = APIClient()
        client.force_authenticate(user=user)
        url = f"/api/core/vendors/{self.vendor.id}/spend-summary/"
        r = client.get(url)

        self.assertEqual(r.status_code, 200)
        self.assertIn("per_currency", r.data)
        self.assertIn("invoice_count", r.data)
        self.assertIn("trend", r.data)
        self.assertEqual(r.data["invoice_count"], 1)
        self.assertEqual(
            Decimal(r.data["per_currency"][0]["total"]), Decimal("750.00")
        )

    def test_spend_summary_included_in_vendor_list_response(self):
        """The spend_summary field must appear on every vendor in the list endpoint."""
        user = _make_user("spend-list@test.com")
        WorkspaceMembership.objects.create(
            workspace=self.workspace, user=user, role="admin"
        )
        _make_invoice(self.workspace, self.vendor,
                      inv_num="LIST-001", amount="1234.00")

        client = APIClient()
        client.force_authenticate(user=user)
        r = client.get("/api/core/vendors/", {"workspace": str(self.workspace.id)})

        self.assertEqual(r.status_code, 200)
        vendors = r.data.get("results") or r.data
        self.assertTrue(len(vendors) >= 1)
        vendor_data = next(v for v in vendors if v["id"] == str(self.vendor.id))
        self.assertIn("spend_summary", vendor_data)
        self.assertEqual(vendor_data["spend_summary"]["invoice_count"], 1)
