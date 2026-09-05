"""
Plays the "partner" system: fires signed webhook events at the local
/webhooks/partner/ endpoint, including replay-attack and storm scenarios
for testing dedup + idempotency.

Usage:
    python scripts/partner_simulator.py normal
    python scripts/partner_simulator.py replay
    python scripts/partner_simulator.py storm --count 50
"""
import argparse
import hashlib
import hmac
import json
import time
import uuid

import requests

WEBHOOK_URL = "http://127.0.0.1/webhooks/partner/"
SECRET = "dev-webhook-secret"  # must match PARTNER_WEBHOOK_SECRET


def sign(body: bytes) -> str:
    return hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()


def build_payload(delivery_id=None):
    return {
        "delivery_id": delivery_id or str(uuid.uuid4()),
        "workspace_slug": "demo",
        "vendor_name": "Acme Supplies",
        "document_type": "po",
        "fields": {
            "po_number": f"PO-{uuid.uuid4().hex[:6].upper()}",
            "order_date": "2026-08-01",
            "currency": "USD",
            "line_items": [{"sku": "WIDGET-1", "description": "Widget", "quantity": 100, "unit_price": 2.5}],
        },
    }


def send(payload):
    body = json.dumps(payload).encode()
    headers = {"Content-Type": "application/json", "X-SCIQ-Signature": sign(body)}
    response = requests.post(WEBHOOK_URL, data=body, headers=headers)
    print(response.status_code, response.text)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario", choices=["normal", "replay", "storm", "bad_signature"])
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()

    if args.scenario == "normal":
        send(build_payload())
    elif args.scenario == "replay":
        payload = build_payload()
        send(payload)
        time.sleep(1)
        send(payload)  # same delivery_id -> should be deduped
    elif args.scenario == "storm":
        payload = build_payload()
        for _ in range(args.count):
            send(payload)  # hammer the same delivery_id concurrently-ish
    elif args.scenario == "bad_signature":
        payload = build_payload()
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json", "X-SCIQ-Signature": "deadbeef"}
        response = requests.post(WEBHOOK_URL, data=body, headers=headers)
        print(response.status_code, response.text)


if __name__ == "__main__":
    main()
