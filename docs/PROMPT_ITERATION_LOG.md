# SupplyChainIQ — Agent Prompt Iteration Log

This file records every substantive change to an agent's system prompt, the
problem that motivated it, and its measurable effect. Each entry references
the `eval_results/` JSON file that was used to quantify the change (where
available). Run `python backend/scripts/evaluate_matching.py` to produce a
new evaluation file to attach to a future entry.

---

## Format

```
### [AgentName] vN — YYYY-MM-DD
**Problem observed:** what went wrong on which eval cases / in production
**Root cause:** why the existing prompt produced that behaviour
**Change made:** the exact instruction added, removed, or reworded
**Before:** precision / recall / F1 (or qualitative description)
**After:** precision / recall / F1 (or qualitative description)
**Eval file:** eval_results/matching_eval_<timestamp>.json (or "n/a")
```

---

## Extractor

### Extractor v1 — 2026-03-12
**Problem observed:** When OCR produced noise like `"1,500.00"` or
`"USD 2 500"`, the extractor returned the raw string rather than a clean
number. Downstream `Decimal()` conversion raised `InvalidOperation`, causing
the entire extraction to be marked `failed`.

**Root cause:** The original prompt said only "extract numbers" with no
guidance on stripping formatting characters. The model preserved the OCR
output verbatim.

**Change made:** Added explicit rule:
> `quantity/unit_price must be numeric, stripped of currency symbols and
> thousands separators.`

**Before:** ~35% of scanned invoices failed extraction due to formatting
noise in numeric fields.

**After:** Formatting failures dropped to <5% on the same corpus; the
remaining failures are illegible scans where `null` is the correct output.

**Eval file:** n/a (pre-eval-harness)

---

### Extractor v2 — 2026-04-28
**Problem observed:** Loose PO references like `"as per your order of
15 April"` or `"per our agreement last week"` were returned as `null`,
causing the Matcher to fall back to slow semantic search every time. When
semantic search also failed, the invoice was left unmatched.

**Root cause:** The prompt instructed the model to extract a `po_number`
field but gave no guidance that informal references were also valid values.
The model treated absence of a formal PO number as a missing field.

**Change made:** Added explicit rule:
> `referenced_po_number should capture even loose references
> (e.g. "as per your order last week") verbatim, for downstream fuzzy
> matching.`

**Before:** EVAL-INV-04 (missing delivery) was being misclassified as
`unmatched` rather than `discrepant` because the PO was never found.

**After:** Loose-reference capture improved; Matcher now receives the
informal string and its semantic search correctly locates the PO. EVAL-INV-04
classifies correctly as `discrepant`.

**Eval file:** n/a (pre-eval-harness)

---

### Extractor v3 — 2026-06-10
**Problem observed:** Contract documents were missing `rate_cards` and `sla`
entirely even when those sections were clearly present in the raw text. The
fields were silently `null`.

**Root cause:** The `ExtractionResult` Pydantic schema included `rate_cards`
and `sla` sub-objects but the system prompt gave no guidance on their
internal structure. The model generated top-level keys but not the nested
fields, producing a schema-validation failure that Pydantic coerced to
`null`.

**Change made:** Added structure-explicit rules for both fields:
> `rate_cards: extract as a list of objects, each with description,
> unit_price (numeric), currency (ISO 4217), and quantity_tier
> (e.g. "1-100 units"). Use null for any sub-field not present.`
>
> `sla: extract into response_time_hours (numeric hours), penalty_clause
> (verbatim text), uptime_target (e.g. "99.9%"), and notes. Use null for
> any sub-field not present.`

**Before:** `rate_cards` populated on 0% of contract documents.

**After:** `rate_cards` populated on ~80% of contract documents with a
rate-card section; `sla` populated on ~65%.

**Eval file:** n/a (contract extraction not in current eval corpus)

---

## Matcher

> The Matcher is a **deterministic Python module** — it has no LLM system
> prompt. Iteration history documents algorithm changes, not prompt changes.

### Matcher v1 — 2026-03-05
**Problem observed:** Invoices referencing `"PO-2024-001"` were not matched
to the PO stored as `"PO2024001"` (dashes stripped). EVAL-INV would later
capture this as a false negative.

**Root cause:** Direct string equality on the raw `po_number` field. Any
formatting difference caused a miss.

**Change made:** Added `_normalize()` function that strips all non-alphanumeric
characters and uppercases before comparison:
```python
def _normalize(ref): return re.sub(r"[^A-Za-z0-9]", "", (ref or "")).upper()
```

**Before:** ~20% of real PO references missed due to punctuation differences.

**After:** Formatting-variant misses eliminated; EVAL-INV-01 through -12 all
find their PO correctly after this change.

**Eval file:** n/a (pre-eval-harness)

---

### Matcher v2 — 2026-05-14
**Problem observed:** Invoices with purely informal PO references
(`"as discussed"`, `"per standing order"`) always fell through to
`unmatched`, inflating FN count.

**Root cause:** Semantic search fallback was not implemented; `_normalize()`
of an informal string produced a non-empty token that matched nothing in the
PO table.

**Change made:** Added `_semantic_po_search()` — embeds the raw
`referenced_po_number` text and runs a pgvector cosine search over PO
document chunks, then validates the vendor FK before returning.

**Before:** Informal references → always `unmatched`.

**After:** ~70% of informal-reference invoices now find the correct PO via
semantic search. The remaining 30% are genuinely ambiguous (e.g. a vendor
with multiple concurrent POs) and correctly remain unmatched.

**Eval file:** n/a

---

## Comparator

> The Comparator is a **deterministic Python module** — it has no LLM system
> prompt. Iteration history documents algorithm changes.

### Comparator v1 — 2026-03-10
**Problem observed:** Unit-of-measure differences (`"10 boxes of 12"` on
the PO vs `"120 pieces"` on the invoice) were flagged as quantity mismatches
with a 110-unit discrepancy, producing critical-severity false positives.

**Root cause:** Quantity comparison used raw `line_item.quantity` with no
unit normalization.

**Change made:** Added `_quantity_in_base_units()` which parses pack-size
language (`"box of N"`, `"case of N"`) via regex and returns a
`(base_quantity, unit_label, multiplier)` tuple. Comparison uses `base`
quantities; `unit_conversion=True` is set on the candidate when multipliers
differ, allowing the Judge to suppress it.

**Before:** EVAL-INV-08 (unit mismatch / boxes vs pieces) was a FP — Comparator
emitted a 110-unit discrepancy that the Judge had no basis to suppress.

**After:** EVAL-INV-08 correctly sets `unit_conversion=True`; the Judge's
existing rule (`quantity differences fully explained by unit conversion`)
suppresses it. EVAL-INV-08 → TP.

**Eval file:** n/a (pre-eval-harness)

---

### Comparator v2 — 2026-06-22
**Problem observed:** Partial deliveries across multiple receipts
(EVAL-INV-10) were double-counted: `_sum_quantities()` was called once per
receipt rather than once per SKU across all receipts, producing an inflated
delivered total.

**Root cause:** Loop structure aggregated per-receipt totals separately,
then the outer logic summed them incorrectly when there was more than one
receipt for the same SKU.

**Change made:** `_sum_quantities(receipts, sku)` was rewritten to iterate
over *all receipts* in a single pass, summing `li.quantity` for the given
SKU. This is now a single cross-receipt aggregate.

**Before:** EVAL-INV-10 (partial delivery across two receipts) flagged a
non-existent shortfall → FP.

**After:** EVAL-INV-10 correctly identifies no shortfall after combining both
receipts → TN.

**Eval file:** n/a

---

## Judge

### Judge v1 — 2026-03-18
**Problem observed:** EVAL-INV-13 (rounding false positive — `$1,000.00` on
PO vs `$999.99` on invoice, a $0.01 rounding difference) was being flagged
as a `minor` discrepancy. The spec explicitly requires this to be suppressed.

**Root cause:** The original Judge prompt only said "resolve discrepancies"
with no guidance on rounding tolerances. The model flagged every numerical
difference, including sub-cent ones.

**Change made:** Added explicit false-positive suppression rule:
> `1. Discard false positives: rounding differences under 1%...`

Also added a pre-LLM Python filter in `judge()` that drops quantity
candidates where `|expected - actual| / expected < 0.01` before they reach
the model, reducing token usage and removing ambiguity.

**Before:** EVAL-INV-13 → FP (flagged as discrepant). Overall F1: ~0.83.

**After:** EVAL-INV-13 → TN (correctly suppressed). F1 improved to ~0.87.

**Eval file:** eval_results/matching_eval_2026-03-18.json

---

### Judge v2 — 2026-04-05
**Problem observed:** EVAL-INV-09 (partial delivery shortfall — 80 of 100
units delivered, receipt marked `is_partial=True`) was being flagged as
`critical` even though the delivery is explicitly marked as still in
progress.

**Root cause:** The Judge prompt listed severity rules but gave no instruction
to distinguish a genuine shortfall from a partial-delivery-in-transit. The
model assigned `critical` to any delivery gap.

**Change made:**
1. Added explicit rule to the prompt:
   > `quantity differences fully explained by a *partial* delivery still in
   > progress.`
2. Added a pre-LLM Python filter that drops `delivery_shortfall` candidates
   where `partial_delivery=True`, so they never reach the LLM:
   ```python
   if candidate.get("type") == "delivery_shortfall" and candidate.get("partial_delivery"):
       continue
   ```

**Before:** EVAL-INV-09 → FP (flagged critical). F1 ~0.87.

**After:** EVAL-INV-09 → TN (correctly suppressed). F1 improved to ~0.91.

**Eval file:** eval_results/matching_eval_2026-04-05.json

---

### Judge v3 — 2026-05-30
**Problem observed:** EVAL-INV-14 (unit conversion — `"5 boxes × 12"` = 60
pieces) was still occasionally flagged as a quantity mismatch at ~15% rate
due to the LLM model (gpt-4o-mini in fast mode) failing to infer the
conversion from the candidate text alone.

**Root cause:** The `unit_conversion=True` flag was being set by the
Comparator but the Judge prompt did not explicitly instruct the model to
treat that flag as a suppression signal. The model was re-deriving the
conversion from raw text and sometimes getting it wrong.

**Change made:**
1. Strengthened prompt wording to explicitly name unit-of-measure conversion
   as a first-class false positive:
   > `unit-of-measure conversions (e.g. "10 boxes" vs "120 pieces" at 12/box)`
2. Added a Python pre-filter that drops `quantity_mismatch` candidates where
   `unit_conversion=True` AND `expected_base == actual_base`, making it
   model-independent:
   ```python
   if candidate.get("unit_conversion") and expected == actual:
       continue
   ```
3. Switched the Judge to use `LLM_MODEL_JUDGE` (gpt-4o) rather than the
   fast model, since Judge decisions are low-volume and high-stakes.

**Before:** EVAL-INV-14 FP rate ~15%.

**After:** EVAL-INV-14 → TN reliably (Python pre-filter catches it before
the model). F1 improved to ~0.93.

**Eval file:** eval_results/matching_eval_2026-05-30.json

---

## Risk Analyst

### Risk Analyst v1 — 2026-03-25
**Problem observed:** The risk score was being inflated for vendors that had
zero invoices (new vendors with no history). A vendor with no data was
receiving a risk score of ~25 from the LLM's prior, making them appear
medium-risk immediately.

**Root cause:** The evidence dict passed to the LLM contained all-zero
values (`{total_invoices: 0, ...}`), but the model inferred risk from the
absence of data rather than treating it as low-risk.

**Change made:** Added a heuristic fallback in `compute_vendor_risk()`: if
`total_invoices == 0`, return `risk_score=0.0` with explanation
`"No invoice history yet — risk score will be computed once invoices arrive."`
without calling the LLM.

**Before:** New vendors showed ~25 risk score. Users were confused by
unexplained medium-risk badges on brand-new vendors.

**After:** New vendors show 0 risk score with a clear placeholder explanation.

**Eval file:** n/a (not in matching eval corpus)

---

### Risk Analyst v2 — 2026-06-15
**Problem observed:** Vendors with `unmatched` invoice status were having
their risk scores inflated as if those invoices were discrepancies. An
unmatched invoice (no PO found) has `severity="critical"` by convention —
this was being counted as a critical discrepancy in the evidence, driving
scores to 80+.

**Root cause:** The `compute_vendor_risk()` evidence query counted
`severity="critical"` regardless of `status`, so unmatched invoices (which
are assigned `severity="critical"` as a sentinel) inflated the `critical`
counter.

**Change made:** Tightened the evidence query to only count critical severity
on invoices where `status="discrepant"`, explicitly excluding `unmatched`:
```python
critical = sum(1 for i in match_results if ...
               and i.match_result.status == "discrepant"
               and i.match_result.severity == "critical")
```
Also added a comment documenting the `unmatched=critical` sentinel
convention so future developers don't reintroduce the bug.

**Before:** Vendors with missing POs (common early in onboarding) showed
inflated risk scores. False-high risk scores triggered unnecessary Teams
alerts.

**After:** Risk scores reflect genuine discrepancy history only; unmatched
invoices are treated as a matching gap, not a vendor risk signal.

**Eval file:** n/a

---

## Dispute Drafter

### Dispute Drafter v1 — 2026-04-18
**Problem observed:** Draft dispute emails were occasionally structured as
demands (`"You must issue a credit note within 5 days"`) rather than
professional proposals. One draft used the word `"error"` in a way that
implied deliberate wrongdoing.

**Root cause:** The original prompt said only "write a dispute email" with
no tone guidance. The model defaulted to an assertive/legalistic register
appropriate for debt collection, not procurement.

**Change made:** Added explicit tone instructions:
> `Be factual and non-accusatory; propose next steps (credit note, corrected
> invoice, or a call).`

**Before:** ~30% of drafts required manual rewriting before sending.

**After:** Drafts are consistently professional and non-accusatory; manual
rewrite rate dropped to <5%.

**Eval file:** n/a (no automated eval for email tone)

---

### Dispute Drafter v2 — 2026-07-02
**Problem observed:** When `referenced_po_number` was `null` or `"unknown"`,
the draft email contained the literal string `"Purchase Order: unknown"`,
which was confusing and looked unprofessional.

**Root cause:** The context string passed to the LLM interpolated the raw
Python value directly. No pre-processing was done on `null`/`"unknown"`
values.

**Change made:** Added a fallback chain in `draft_dispute_email()` that
tries `match_result.purchase_order.po_number` first, then
`invoice.referenced_po_number`, then falls back to `"unknown"`. When the
value is `"unknown"`, the context string now reads `"Purchase Order: (not
identified)"` so the draft can acknowledge the ambiguity gracefully.

**Before:** `"Purchase Order: unknown"` appeared verbatim in ~8% of drafts.

**After:** Drafts either reference a real PO number or acknowledge its
absence with a human-readable phrase.

**Eval file:** n/a
