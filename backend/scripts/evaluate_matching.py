"""Run the three-way agent orchestrator over the seeded evaluation corpus."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from django.core.management.base import BaseCommand

from apps.agents.orchestrator import run_three_way_match
from apps.documents.models import Invoice


PLANTED = {
    "EVAL-INV-01": True,
    "EVAL-INV-02": True,
    "EVAL-INV-03": True,
    "EVAL-INV-04": True,
    "EVAL-INV-05": True,
    "EVAL-INV-06": True,
    "EVAL-INV-07": True,
    "EVAL-INV-08": False,
    "EVAL-INV-09": False,
    "EVAL-INV-10": False,
}


class Command(BaseCommand):
    help = "Evaluate the agent orchestrator against the seeded corpus."

    def handle(self, *args, **options):
        tp = fp = fn = 0
        rows = []
        for invoice in Invoice.objects.filter(invoice_number__startswith="EVAL-INV-").select_related("vendor", "workspace"):
            expected = PLANTED[invoice.invoice_number]
            result = run_three_way_match(invoice)
            flagged = result["status"] == "discrepant"
            if flagged and expected:
                tp += 1
            elif flagged and not expected:
                fp += 1
            elif not flagged and expected:
                fn += 1
            rows.append((invoice.invoice_number, expected, result["status"], result["severity"]))

        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 1.0
        for row in rows:
            self.stdout.write(f"{row[0]} expected={row[1]} status={row[2]} severity={row[3]}")
        self.stdout.write(f"TP={tp} FP={fp} FN={fn}")
        self.stdout.write(f"precision={precision:.3f} recall={recall:.3f}")


if __name__ == "__main__":
    Command().handle()
