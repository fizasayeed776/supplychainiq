"""Run the three-way agent orchestrator over the seeded evaluation corpus.

Ground truth
============
Cases 01-12  DISCREPANT  (planted discrepancy present)
Cases 13-15  CLEAN       (should match cleanly)

Discrepancy taxonomy:
  01 quantity_mismatch
  02 rate_mismatch
  03 currency_mismatch
  04 missing_delivery
  05 contract_rate_violation
  06 multi_field (qty + rate + currency)
  07 expired_contract
  08 unit_mismatch (boxes vs pieces, wrong count)
  09 partial_delivery_shortfall
  10 partial_delivery_multi_receipt
  11 zero_quantity_line
  12 multi_currency_lines
  13 rounding_false_positive (CLEAN)
  14 unit_conversion (CLEAN)
  15 full_match (CLEAN)

Usage
=====
  # default output path (eval_results/matching_eval_<timestamp>.json)
  python backend/scripts/evaluate_matching.py

  # custom output path
  python backend/scripts/evaluate_matching.py --output /tmp/my_eval.json

  # suppress JSON output (console only)
  python backend/scripts/evaluate_matching.py --no-output

The JSON file is always written unless --no-output is supplied.  Each run
produces a new timestamped file so results are never overwritten, giving
a persistent, comparable record across prompt iterations.  Reference the
filename in docs/PROMPT_ITERATION_LOG.md for each entry that changes agent
behaviour.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django

django.setup()

from apps.agents.orchestrator import run_three_way_match
from apps.documents.models import Invoice


# True  = a genuine discrepancy is present and the agent SHOULD flag it.
# False = the invoice is clean and the agent SHOULD NOT flag it.
PLANTED = {
    "EVAL-INV-01": True,   # quantity mismatch
    "EVAL-INV-02": True,   # rate mismatch
    "EVAL-INV-03": True,   # currency mismatch
    "EVAL-INV-04": True,   # missing delivery
    "EVAL-INV-05": True,   # contract rate violation
    "EVAL-INV-06": True,   # multi-field (qty + rate + currency)
    "EVAL-INV-07": True,   # expired contract
    "EVAL-INV-08": True,   # unit mismatch (boxes vs pieces)
    "EVAL-INV-09": True,   # partial delivery shortfall
    "EVAL-INV-10": True,   # partial delivery across two receipts
    "EVAL-INV-11": True,   # zero quantity line
    "EVAL-INV-12": True,   # multi-currency lines
    "EVAL-INV-13": False,  # rounding false positive — should be suppressed
    "EVAL-INV-14": False,  # unit conversion (60 pieces = 5 boxes x 12)
    "EVAL-INV-15": False,  # full match — everything correct
}

# Default output directory, relative to repo root (backend/../eval_results/).
# Use an absolute path so the script works regardless of working directory.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DEFAULT_OUTPUT_DIR = os.path.join(_REPO_ROOT, "eval_results")


def _default_output_path() -> str:
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return os.path.join(DEFAULT_OUTPUT_DIR, f"matching_eval_{ts}.json")


def _write_json(path: str, payload: dict) -> None:
    """Write *payload* as pretty-printed JSON to *path*, creating parent dirs."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)


class Command:
    def handle(self, output_path: str | None = None) -> dict:
        """Run the evaluation and return the results dict.

        Args:
            output_path: where to write JSON results, or None to skip writing.

        Returns:
            The full results dict (same data written to JSON).
        """
        started_at = datetime.now(tz=timezone.utc).isoformat()
        tp = fp = fn = tn = 0
        rows = []

        invoices = (
            Invoice.objects
            .filter(invoice_number__startswith="EVAL-INV-")
            .select_related("vendor", "workspace")
            .order_by("invoice_number")
        )

        for invoice in invoices:
            inv_num = invoice.invoice_number
            if inv_num not in PLANTED:
                print(f"WARNING: {inv_num} not in PLANTED dict — skipping")
                continue

            expected_discrepant = PLANTED[inv_num]
            result = run_three_way_match(invoice)
            actually_discrepant = result["status"] == "discrepant"

            if actually_discrepant and expected_discrepant:
                tp += 1
                label = "TP"
            elif actually_discrepant and not expected_discrepant:
                fp += 1
                label = "FP"
            elif not actually_discrepant and expected_discrepant:
                fn += 1
                label = "FN"
            else:
                tn += 1
                label = "TN"

            rows.append({
                "invoice_number":      inv_num,
                "expected_discrepant": expected_discrepant,
                "got_status":          result["status"],
                "got_severity":        result["severity"],
                "label":               label,
                "discrepancies":       result.get("discrepancies", []),
                "reasoning":           result.get("reasoning", ""),
            })

        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall    = tp / (tp + fn) if (tp + fn) else 1.0
        f1        = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        n_discrepant = sum(PLANTED.values())
        n_clean      = sum(1 for v in PLANTED.values() if not v)

        # ── Console output (unchanged from original) ──────────────────────
        print("\n── Per-invoice results ────────────────────────────────────────")
        for row in rows:
            print(f"  {row['invoice_number']}  "
                  f"expected={'discrepant' if row['expected_discrepant'] else 'clean':11s}  "
                  f"got={row['got_status']:11s}  "
                  f"severity={row['got_severity']:8s}  "
                  f"[{row['label']}]")

        print("\n── Confusion matrix ───────────────────────────────────────────")
        print(f"  TP={tp}  FP={fp}  FN={fn}  TN={tn}")
        print(f"  precision={precision:.3f}  recall={recall:.3f}  F1={f1:.3f}")
        print(f"  Total evaluated: {len(rows)} invoices ({n_discrepant} discrepant, "
              f"{n_clean} clean)")

        # ── Build results dict ────────────────────────────────────────────
        results = {
            "meta": {
                "started_at":         started_at,
                "finished_at":        datetime.now(tz=timezone.utc).isoformat(),
                "script":             __file__,
                "corpus_size":        len(PLANTED),
                "evaluated":          len(rows),
                "n_discrepant_cases": n_discrepant,
                "n_clean_cases":      n_clean,
            },
            "confusion_matrix": {
                "TP": tp,
                "FP": fp,
                "FN": fn,
                "TN": tn,
            },
            "metrics": {
                "precision": round(precision, 4),
                "recall":    round(recall,    4),
                "f1":        round(f1,        4),
            },
            "per_invoice": rows,
        }

        # ── JSON persistence ──────────────────────────────────────────────
        if output_path is not None:
            _write_json(output_path, results)
            print(f"\n── Results written to: {output_path}")

        return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate the three-way matching agent pipeline against the seeded corpus.",
    )
    parser.add_argument(
        "--output",
        metavar="PATH",
        default=None,
        help=(
            "Path for the JSON output file "
            f"(default: {os.path.join('eval_results', 'matching_eval_<timestamp>.json')})"
        ),
    )
    parser.add_argument(
        "--no-output",
        action="store_true",
        default=False,
        help="Print results to console only; do not write a JSON file.",
    )
    args = parser.parse_args()

    if args.no_output:
        output_path = None
    elif args.output:
        output_path = args.output
    else:
        output_path = _default_output_path()

    Command().handle(output_path=output_path)


if __name__ == "__main__":
    main()
