"""
Management command: report_llm_usage

Usage:
    python manage.py report_llm_usage
    python manage.py report_llm_usage --month 2026-09

Prints a summary table of LLM/embedding usage for the given month (default:
current month), including total calls, cache hit rate, estimated spend, and
whether spend is within LLM_MONTHLY_USAGE_CAP_USD.
"""
from django.core.management.base import BaseCommand

from apps.agents.usage import get_monthly_stats


class Command(BaseCommand):
    help = "Report LLM/embedding call counts, cache hit rate, and estimated cost for a given month."

    def add_arguments(self, parser):
        parser.add_argument(
            "--month",
            default=None,
            help="Month to report in YYYY-MM format (default: current month).",
        )

    def handle(self, *args, **options):
        month = options.get("month")
        stats = get_monthly_stats(month=month)

        cap_status = "✓ within cap" if stats["within_cap"] else "✗ CAP EXCEEDED"
        self.stdout.write("")
        self.stdout.write(self.style.HTTP_INFO("── LLM Usage Report ──────────────────────────────"))
        self.stdout.write(f"  Month                : {stats['month']}")
        self.stdout.write(f"  Complete calls       : {stats['calls_complete']}")
        self.stdout.write(f"  Complete cache hits  : {stats['hits_complete']}")
        self.stdout.write(f"  Embed calls          : {stats['calls_embed']}")
        self.stdout.write(f"  Embed cache hits     : {stats['hits_embed']}")
        self.stdout.write(f"  Total calls          : {stats['total_calls']}")
        self.stdout.write(f"  Cache hit rate       : {stats['cache_hit_rate_pct']}%")
        self.stdout.write(f"  Approx tokens        : {stats['tokens_approx']:,}")
        self.stdout.write(f"  Estimated spend      : ${stats['estimated_cost_usd']:.4f}")
        self.stdout.write(f"  Monthly cap          : ${stats['monthly_cap_usd']:.2f}")
        if stats["within_cap"]:
            self.stdout.write(f"  Cap status           : {self.style.SUCCESS(cap_status)}")
        else:
            self.stdout.write(f"  Cap status           : {self.style.ERROR(cap_status)}")
        self.stdout.write(self.style.HTTP_INFO("───────────────────────────────────────────────────"))
        self.stdout.write("")
