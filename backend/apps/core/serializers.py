from decimal import Decimal
from django.db.models import Sum, Count
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework import serializers
from .models import Workspace, Vendor, Contract


class WorkspaceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Workspace
        fields = ["id", "name", "slug", "settings_json", "created_at"]


def _compute_spend_summary(vendor) -> dict:
    """Aggregate Invoice totals for *vendor*, grouped by currency.

    Returns a dict with:
      - per_currency: [{currency, total, invoice_count}]  (one entry per ISO code)
      - invoice_count: total across all currencies
      - this_quarter_usd_equivalent: null (FX conversion not attempted — raw totals reported)
      - trend: {this_quarter, last_quarter, currency} for the vendor's primary currency,
               or null when fewer than two quarters of data exist
    """
    from apps.documents.models import Invoice

    now = timezone.now().date()
    # Quarter boundaries (calendar quarters)
    q_month = ((now.month - 1) // 3) * 3 + 1  # first month of current quarter
    import datetime
    this_q_start = datetime.date(now.year, q_month, 1)
    # Last-quarter start: go back 3 months from this_q_start
    lq_year = now.year if q_month > 3 else now.year - 1
    lq_month = q_month - 3 if q_month > 3 else q_month + 9
    last_q_start = datetime.date(lq_year, lq_month, 1)

    invoices = Invoice.objects.filter(vendor=vendor)

    # Per-currency totals
    rows = (
        invoices
        .values("currency")
        .annotate(
            total=Coalesce(Sum("total_amount"), Decimal("0")),
            invoice_count=Count("id"),
        )
        .order_by("-total")
    )
    per_currency = [
        {
            "currency": r["currency"] or "USD",
            "total": str(r["total"]),
            "invoice_count": r["invoice_count"],
        }
        for r in rows
    ]
    total_invoices = sum(r["invoice_count"] for r in per_currency)

    # Trend: this quarter vs last quarter in the primary (first) currency
    trend = None
    if per_currency:
        primary_currency = per_currency[0]["currency"]
        this_q_total = (
            invoices
            .filter(currency=primary_currency, invoice_date__gte=this_q_start)
            .aggregate(total=Coalesce(Sum("total_amount"), Decimal("0")))
        )["total"]
        last_q_total = (
            invoices
            .filter(
                currency=primary_currency,
                invoice_date__gte=last_q_start,
                invoice_date__lt=this_q_start,
            )
            .aggregate(total=Coalesce(Sum("total_amount"), Decimal("0")))
        )["total"]
        if this_q_total or last_q_total:
            trend = {
                "currency": primary_currency,
                "this_quarter": str(this_q_total),
                "last_quarter": str(last_q_total),
                "change_pct": (
                    round(float((this_q_total - last_q_total) / last_q_total * 100), 1)
                    if last_q_total else None
                ),
            }

    return {
        "per_currency": per_currency,
        "invoice_count": total_invoices,
        "trend": trend,
    }


class VendorSerializer(serializers.ModelSerializer):
    spend_summary = serializers.SerializerMethodField()

    class Meta:
        model = Vendor
        fields = [
            "id", "workspace", "name", "contacts", "payment_terms_days",
            "risk_score", "risk_factors", "risk_explanation", "risk_updated_at",
            "spend_summary", "created_at",
        ]
        read_only_fields = [
            "risk_score", "risk_factors", "risk_explanation", "risk_updated_at",
            "spend_summary",
        ]

    def get_spend_summary(self, vendor):
        return _compute_spend_summary(vendor)


class ContractSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source="vendor.name", read_only=True)

    class Meta:
        model = Contract
        fields = [
            "id", "workspace", "vendor", "vendor_name", "file", "terms",
            "valid_from", "valid_until", "status", "created_at",
        ]
