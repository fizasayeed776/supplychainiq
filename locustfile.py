"""
SupplyChainIQ — Locust load-test for the document ingestion pipeline.

Covers the end-to-end hot path:
  1. Register a fresh user + workspace (once per simulated user)
  2. Upload a document (PDF or plain-text invoice stub)
  3. Poll the document status until extraction completes or times out
  4. Optionally open a WebSocket connection to the dashboard feed and
     listen for pipeline_progress events while an upload is in flight

Usage
=====
  # Install Locust (not in requirements.txt — dev/perf testing only)
  pip install locust==2.31.6 websocket-client==1.8.0

  # Run headless against a local docker-compose stack
  locust --headless -u 10 -r 2 --run-time 60s \
         --host http://localhost \
         --csv load_results/ingestion_$(date +%Y%m%dT%H%M%S)

  # Run with the web UI for interactive analysis
  locust --host http://localhost

Scenarios
=========
  DocumentIngestionUser   — full upload → poll cycle (weight 8)
  DashboardWebSocketUser  — WebSocket observer listening for events (weight 2)

Environment variables
=====================
  LOCUST_BASE_URL     override the --host flag (useful in CI)
  LOCUST_PDF_PATH     local path to a real PDF to upload (default: generates
                      a synthetic invoice stub as a plain-text file)
"""
from __future__ import annotations

import io
import os
import random
import string
import time
import uuid

from locust import HttpUser, TaskSet, between, task, events
from locust.exception import RescheduleTask

# ---------------------------------------------------------------------------
# Synthetic invoice content (used when no real PDF is provided)
# ---------------------------------------------------------------------------
_INVOICE_TEXT = """\
INVOICE

From: Test Vendor Ltd
To:   SupplyChainIQ Demo Inc.
Invoice #: INV-{num}
Date: 2026-09-01
PO Reference: PO-2026-{num}

Line items:
  SKU-A    Consulting services    10 hours @ $150.00    = $1,500.00
  SKU-B    Software licence       1 unit  @ $500.00    =   $500.00

Total: $2,000.00 USD
Payment terms: 30 days
"""

_PDF_PATH = os.environ.get("LOCUST_PDF_PATH", "")


def _invoice_file(num: int) -> tuple[str, bytes, str]:
    """Return (filename, file_bytes, mime_type)."""
    if _PDF_PATH and os.path.exists(_PDF_PATH):
        with open(_PDF_PATH, "rb") as fh:
            return (os.path.basename(_PDF_PATH), fh.read(), "application/pdf")
    content = _INVOICE_TEXT.format(num=num).encode()
    return (f"invoice_{num}.txt", content, "text/plain")


def _rand_suffix(n: int = 6) -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=n))


# ---------------------------------------------------------------------------
# Shared state (populated during on_start, reused across tasks)
# ---------------------------------------------------------------------------
class _State:
    access_token: str = ""
    workspace_id: str = ""
    upload_count: int = 0


# ---------------------------------------------------------------------------
# TaskSet: document upload + status polling
# ---------------------------------------------------------------------------
class DocumentIngestionTaskSet(TaskSet):
    """Upload a document and poll until it reaches a terminal OCR/extraction state."""

    TERMINAL_OCR = {"not_needed", "done", "low_confidence", "failed"}
    TERMINAL_EXT = {"done", "failed"}
    POLL_INTERVAL = 0.5   # seconds between status polls
    POLL_TIMEOUT  = 30.0  # give up after 30 s

    def on_start(self):
        self._state = _State()
        self._register_and_login()

    # ── Auth ──────────────────────────────────────────────────────────────

    def _register_and_login(self):
        suffix = _rand_suffix()
        email = f"load_{suffix}@locust.test"
        payload = {
            "email": email,
            "password": "Locust!Pass#99",
            "full_name": f"Load Tester {suffix}",
            "workspace_name": f"Locust WS {suffix}",
        }
        with self.client.post(
            "/api/auth/register/",
            json=payload,
            name="/api/auth/register/",
            catch_response=True,
        ) as r:
            if r.status_code == 201:
                data = r.json()
                self._state.access_token = data["access"]
                self._state.workspace_id = data["workspace"]["id"]
            else:
                r.failure(f"Registration failed: {r.status_code} {r.text[:200]}")
                raise RescheduleTask()

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self._state.access_token}"}

    # ── Tasks ─────────────────────────────────────────────────────────────

    @task(8)
    def upload_and_poll(self):
        """Upload a synthetic invoice, then poll for completion."""
        self._state.upload_count += 1
        num = self._state.upload_count
        filename, content, mime = _invoice_file(num)

        # Upload
        with self.client.post(
            "/api/documents/documents/",
            files={"file": (filename, io.BytesIO(content), mime)},
            data={
                "workspace": self._state.workspace_id,
                "type": "invoice",
            },
            headers=self._auth_headers(),
            name="/api/documents/documents/ [upload]",
            catch_response=True,
        ) as r:
            if r.status_code not in (201, 409):
                r.failure(f"Upload failed: {r.status_code} {r.text[:200]}")
                return
            if r.status_code == 409:
                # Duplicate — perfectly valid; just skip polling
                return
            doc_id = r.json()["id"]

        # Poll until terminal state or timeout
        deadline = time.monotonic() + self.POLL_TIMEOUT
        while time.monotonic() < deadline:
            with self.client.get(
                f"/api/documents/documents/{doc_id}/",
                headers=self._auth_headers(),
                name="/api/documents/documents/{id}/ [poll]",
                catch_response=True,
            ) as r:
                if r.status_code != 200:
                    r.failure(f"Poll returned {r.status_code}")
                    return
                doc = r.json()
                ocr_done = doc.get("ocr_status") in self.TERMINAL_OCR
                ext_done = doc.get("extraction_status") in self.TERMINAL_EXT
                if ocr_done and ext_done:
                    return  # success — Locust records the poll as OK
            time.sleep(self.POLL_INTERVAL)

        # Timed out — record as a soft failure (not a Locust error) so the
        # request count is still incremented; log a custom event instead.
        events.request.fire(
            request_type="POLL_TIMEOUT",
            name="document_processing_timeout",
            response_time=self.POLL_TIMEOUT * 1000,
            response_length=0,
            exception=TimeoutError(f"doc {doc_id} did not finish in {self.POLL_TIMEOUT}s"),
            context={},
        )

    @task(2)
    def list_documents(self):
        """Read the document list (simulates UI refresh polling)."""
        self.client.get(
            "/api/documents/documents/",
            params={"workspace": self._state.workspace_id},
            headers=self._auth_headers(),
            name="/api/documents/documents/ [list]",
        )

    @task(1)
    def list_vendors(self):
        """Read the vendor list including spend_summary (exercises the new endpoint)."""
        self.client.get(
            "/api/core/vendors/",
            params={"workspace": self._state.workspace_id},
            headers=self._auth_headers(),
            name="/api/core/vendors/ [list]",
        )


# ---------------------------------------------------------------------------
# TaskSet: WebSocket dashboard observer
# ---------------------------------------------------------------------------
class DashboardWebSocketTaskSet(TaskSet):
    """Connect to the dashboard WebSocket feed and count pipeline_progress events.

    Uses websocket-client (sync) rather than asyncio so it works inside Locust's
    green-thread model without patching.
    """

    def on_start(self):
        self._state = _State()
        self._ws = None
        self._register_and_get_token()
        self._connect_ws()

    def _register_and_get_token(self):
        suffix = _rand_suffix()
        email = f"ws_{suffix}@locust.test"
        r = self.client.post("/api/auth/register/", json={
            "email": email, "password": "Locust!Pass#99",
            "full_name": f"WS Tester {suffix}",
            "workspace_name": f"WS Locust {suffix}",
        }, name="/api/auth/register/ [ws_user]")
        if r.status_code == 201:
            data = r.json()
            self._state.access_token = data["access"]
            self._state.workspace_id = data["workspace"]["id"]

    def _connect_ws(self):
        try:
            import websocket
        except ImportError:
            # websocket-client not installed — skip WebSocket tasks gracefully
            self._ws = None
            return

        host = self.user.host.replace("http://", "ws://").replace("https://", "wss://")
        ws_url = f"{host}/ws/dashboard/{self._state.workspace_id}/?token={self._state.access_token}"
        try:
            self._ws = websocket.create_connection(ws_url, timeout=5)
        except Exception:
            self._ws = None

    @task
    def receive_events(self):
        """Read up to 5 messages from the WebSocket (non-blocking attempt)."""
        if self._ws is None:
            time.sleep(2)
            return
        try:
            self._ws.settimeout(2.0)
            for _ in range(5):
                msg = self._ws.recv()
                if not msg:
                    break
        except Exception:
            # Timeout / closed connection is expected when no events are in flight
            pass

    def on_stop(self):
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Locust user classes (weight controls relative spawn rate)
# ---------------------------------------------------------------------------
class DocumentIngestionUser(HttpUser):
    """Simulates a procurement user uploading and tracking documents."""
    tasks = [DocumentIngestionTaskSet]
    wait_time = between(1, 4)
    weight = 8


class DashboardWebSocketUser(HttpUser):
    """Simulates a dashboard observer watching the pipeline feed via WebSocket."""
    tasks = [DashboardWebSocketTaskSet]
    wait_time = between(2, 6)
    weight = 2
