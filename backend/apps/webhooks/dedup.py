"""
Inbound webhook deduplication. A partner may redeliver the same event
(network retries, at-least-once delivery) — dedupe by a delivery ID stored
in Redis with a TTL, so replay attacks / storms don't cause double-processing.
"""
from django.core.cache import cache

DEDUP_TTL_SECONDS = 60 * 60 * 24  # 24h window is generous for partner retries


def is_duplicate_delivery(delivery_id: str) -> bool:
    key = f"webhook_dedup:{delivery_id}"
    added = cache.add(key, True, timeout=DEDUP_TTL_SECONDS)  # atomic: True only if key was NOT already set
    return not added
