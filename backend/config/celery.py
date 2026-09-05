import os
from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("supplychainiq")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
app.conf.imports = ("apps.agents.tasks",)

app.conf.beat_schedule = {
    "daily-fx-rate-sync": {
        "task": "apps.workflow.tasks.sync_fx_rates",
        "schedule": crontab(hour=2, minute=0),
    },
    "nightly-full-rematch": {
        "task": "apps.matching.tasks.rematch_all_open_invoices",
        "schedule": crontab(hour=3, minute=0),
    },
    "contract-expiry-checker": {
        "task": "apps.workflow.tasks.check_contract_expiry",
        "schedule": crontab(hour=6, minute=0),
    },
    "weekly-compliance-report": {
        "task": "apps.workflow.tasks.send_weekly_compliance_report",
        "schedule": crontab(hour=7, minute=0, day_of_week=1),
    },
    "escalate-overdue-approvals": {
        "task": "apps.workflow.tasks.escalate_overdue_steps",
        "schedule": crontab(minute="*/15"),
    },
    "recompute-vendor-risk": {
        "task": "apps.agents.tasks.recompute_all_vendor_risk",
        "schedule": crontab(hour=4, minute=0),
    },
    "poll-mailpit-inbox": {
        "task": "apps.documents.tasks.poll_mailpit",
        "schedule": crontab(minute="*/1"),
    },
}


@app.task(bind=True)
def debug_task(self):
    print(f"Request: {self.request!r}")
