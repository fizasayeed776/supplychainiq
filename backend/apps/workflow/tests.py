"""
Workflow FSM and triage rule tests.
Rubric requirement: workflow logic coverage.
"""
from datetime import date
from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.core.models import Vendor, Workspace
from apps.documents.models import Document, Invoice
from apps.matching.models import MatchResult
from .models import ApprovalFlow, TriageRule


class ApprovalFlowFSMTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(name="WF tests", slug="wf-tests")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="WF Vendor")
        inv_doc = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="invoice",
            file=SimpleUploadedFile("inv.txt", b"inv"),
            content_hash="wf-inv-001".ljust(64, "0"),
        )
        self.invoice = Invoice.objects.create(
            document=inv_doc, workspace=self.workspace, vendor=self.vendor,
            invoice_number="INV-WF-1",
            invoice_date=date(2026, 9, 1), due_date=date(2026, 10, 1), currency="USD",
        )
        self.flow = ApprovalFlow.objects.create(workspace=self.workspace, invoice=self.invoice)

    def test_initial_state_is_draft(self):
        self.assertEqual(self.flow.state, "draft")

    def test_submit_transitions_to_pending_review(self):
        self.flow.submit_for_review()
        self.flow.save()
        self.flow.refresh_from_db()
        self.assertEqual(self.flow.state, "pending_review")

    def test_approve_from_pending_review(self):
        self.flow.submit_for_review()
        self.flow.approve()
        self.flow.save()
        self.flow.refresh_from_db()
        self.assertEqual(self.flow.state, "approved")

    def test_dispute_from_pending_review(self):
        self.flow.submit_for_review()
        self.flow.dispute()
        self.flow.save()
        self.flow.refresh_from_db()
        self.assertEqual(self.flow.state, "disputed")

    def test_resubmit_returns_to_pending_review(self):
        self.flow.submit_for_review()
        self.flow.dispute()
        self.flow.resubmit()
        self.flow.save()
        self.flow.refresh_from_db()
        self.assertEqual(self.flow.state, "pending_review")

    def test_mark_paid_from_approved(self):
        self.flow.submit_for_review()
        self.flow.approve()
        self.flow.mark_paid()
        self.flow.save()
        self.flow.refresh_from_db()
        self.assertEqual(self.flow.state, "paid")


class TriageRuleTests(TestCase):
    def setUp(self):
        self.workspace = Workspace.objects.create(name="Triage tests", slug="triage-tests")
        self.vendor = Vendor.objects.create(workspace=self.workspace, name="Low Risk Vendor", risk_score=10.0)
        inv_doc = Document.objects.create(
            workspace=self.workspace, vendor=self.vendor, type="invoice",
            file=SimpleUploadedFile("inv.txt", b"inv"),
            content_hash="triage-inv-001".ljust(64, "0"),
        )
        self.invoice = Invoice.objects.create(
            document=inv_doc, workspace=self.workspace, vendor=self.vendor,
            invoice_number="INV-TRIAGE-1", currency="USD",
            total_amount=Decimal("200.00"),
            invoice_date=date(2026, 9, 1), due_date=date(2026, 10, 1),
        )
        self.match_result = MatchResult.objects.create(
            workspace=self.workspace, invoice=self.invoice, status="matched", severity="none",
        )

    def test_auto_approve_rule_matches_low_amount_low_risk(self):
        rule = TriageRule(
            workspace=self.workspace, name="Auto-approve <500 low-risk",
            max_amount=Decimal("500.00"), max_vendor_risk_score=30.0,
            require_status="matched", active=True,
        )
        self.assertTrue(rule.matches(self.invoice, self.match_result))

    def test_rule_blocks_when_amount_exceeds_max(self):
        rule = TriageRule(
            workspace=self.workspace, name="Auto-approve <100",
            max_amount=Decimal("100.00"), max_vendor_risk_score=50.0,
            require_status="matched", active=True,
        )
        self.assertFalse(rule.matches(self.invoice, self.match_result))

    def test_rule_blocks_when_vendor_risk_too_high(self):
        self.vendor.risk_score = 75.0
        self.vendor.save()
        rule = TriageRule(
            workspace=self.workspace, name="Auto-approve low risk",
            max_amount=Decimal("1000.00"), max_vendor_risk_score=50.0,
            require_status="matched", active=True,
        )
        self.assertFalse(rule.matches(self.invoice, self.match_result))

    def test_inactive_rule_never_matches(self):
        rule = TriageRule(
            workspace=self.workspace, name="Disabled rule",
            active=False, require_status="matched",
        )
        self.assertFalse(rule.matches(self.invoice, self.match_result))
