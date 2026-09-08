from celery import shared_task
from apps.core.models import Vendor


@shared_task(bind=True, max_retries=3, retry_backoff=True)
def recompute_vendor_risk(self, vendor_id):
    from .risk_analyst import compute_vendor_risk
    from django.utils.dateparse import parse_datetime

    vendor = Vendor.objects.get(id=vendor_id)
    try:
        result = compute_vendor_risk(vendor)
        vendor.risk_score = result["risk_score"]
        vendor.risk_factors = result["risk_factors"]
        vendor.risk_explanation = result["explanation"]
        vendor.risk_updated_at = parse_datetime(result["computed_at"])
        vendor.save(update_fields=["risk_score", "risk_factors", "risk_explanation", "risk_updated_at"])
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc)


@shared_task
def recompute_all_vendor_risk():
    """Beat schedule: nightly risk recompute for every vendor."""
    ids = list(Vendor.objects.values_list("id", flat=True))
    for vendor_id in ids:
        recompute_vendor_risk.delay(str(vendor_id))
    return {"queued": len(ids)}
