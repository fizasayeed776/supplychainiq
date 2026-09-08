"""
Excel export for the weekly compliance report.

Produces an .xlsx workbook with three sheets:
  1. Summary     — headline KPIs (one row of stats per workspace)
  2. Discrepancies — every open discrepant MatchResult with invoice details
  3. Contracts   — contracts expiring within 60 days or already expired

Usage (called from send_weekly_compliance_report task):
    from apps.workflow.report_export import build_compliance_workbook
    wb_bytes = build_compliance_workbook(workspace, stats)
    # attach wb_bytes as compliance_report.xlsx to the EmailMultiAlternatives

The module is deliberately dependency-light: only openpyxl (already in
requirements.txt) and stdlib.  No Django template engine needed.
"""
from __future__ import annotations

import io
from datetime import date, timedelta

from django.utils import timezone

try:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    _OPENPYXL_AVAILABLE = True
except ImportError:
    _OPENPYXL_AVAILABLE = False


# ---------------------------------------------------------------------------
# Colour palette (hex without #, openpyxl format)
# ---------------------------------------------------------------------------
_CLR_HEADER_BG  = "1A3C5E"   # dark navy
_CLR_HEADER_FG  = "FFFFFF"   # white
_CLR_CRITICAL   = "C0392B"   # red
_CLR_MAJOR      = "E67E22"   # orange
_CLR_MINOR      = "F1C40F"   # yellow
_CLR_MATCHED    = "27AE60"   # green
_CLR_ALT_ROW    = "F2F6FA"   # light blue-grey for alternating rows


def _header_row(ws, columns: list[str]) -> None:
    """Write a styled header row to worksheet *ws*."""
    fill = PatternFill("solid", fgColor=_CLR_HEADER_BG)
    font = Font(bold=True, color=_CLR_HEADER_FG, size=10)
    for col_idx, name in enumerate(columns, start=1):
        cell = ws.cell(row=1, column=col_idx, value=name)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 28


def _auto_width(ws) -> None:
    """Set column widths based on max content length (capped at 55 chars)."""
    for col in ws.columns:
        max_len = max(
            (len(str(cell.value or "")) for cell in col),
            default=8,
        )
        ws.column_dimensions[get_column_letter(col[0].column)].width = min(max_len + 4, 55)


def _severity_fill(severity: str) -> PatternFill | None:
    colour = {
        "critical": _CLR_CRITICAL,
        "major":    _CLR_MAJOR,
        "minor":    _CLR_MINOR,
    }.get(severity)
    return PatternFill("solid", fgColor=colour) if colour else None


# ---------------------------------------------------------------------------
# Sheet builders
# ---------------------------------------------------------------------------

def _sheet_summary(wb, workspace, stats: dict) -> None:
    ws = wb.create_sheet("Summary")
    ws.sheet_view.showGridLines = False

    # Title band
    ws.merge_cells("A1:F1")
    title_cell = ws["A1"]
    title_cell.value = f"SupplyChainIQ — Weekly Compliance Report: {workspace.name}"
    title_cell.font = Font(bold=True, size=13, color=_CLR_HEADER_BG)
    title_cell.alignment = Alignment(horizontal="left", vertical="center")
    ws.row_dimensions[1].height = 32

    ws.merge_cells("A2:F2")
    ws["A2"].value = f"Generated: {timezone.now().strftime('%Y-%m-%d %H:%M UTC')}"
    ws["A2"].font = Font(italic=True, size=9, color="888888")
    ws.row_dimensions[2].height = 16

    # KPI table header
    headers = ["Metric", "Value"]
    fill = PatternFill("solid", fgColor=_CLR_HEADER_BG)
    font = Font(bold=True, color=_CLR_HEADER_FG, size=10)
    for col_idx, h in enumerate(headers, start=1):
        c = ws.cell(row=4, column=col_idx, value=h)
        c.fill = fill
        c.font = font
        c.alignment = Alignment(horizontal="center")
    ws.row_dimensions[4].height = 22

    kpis = [
        ("Total invoices this week",     stats.get("total_invoices", 0)),
        ("Discrepant invoices",          stats.get("discrepant", 0)),
        ("Critical discrepancies",       stats.get("critical", 0)),
        ("Expired contracts",            stats.get("expired_contracts", 0)),
        ("Vendors with open disputes",   stats.get("open_disputes", 0)),
    ]
    alt_fill = PatternFill("solid", fgColor=_CLR_ALT_ROW)
    for row_offset, (metric, value) in enumerate(kpis):
        row = 5 + row_offset
        ws.cell(row=row, column=1, value=metric).font = Font(size=10)
        val_cell = ws.cell(row=row, column=2, value=value)
        val_cell.font = Font(bold=True, size=10)
        val_cell.alignment = Alignment(horizontal="center")
        if row_offset % 2 == 1:
            for col in (1, 2):
                ws.cell(row=row, column=col).fill = alt_fill

    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 14


def _sheet_discrepancies(wb, workspace) -> None:
    from apps.matching.models import MatchResult

    ws = wb.create_sheet("Discrepancies")
    ws.sheet_view.showGridLines = False

    cols = [
        "Invoice #", "Vendor", "Invoice Date", "Due Date",
        "Currency", "Amount", "Severity", "Status", "Summary",
    ]
    _header_row(ws, cols)

    results = (
        MatchResult.objects
        .filter(workspace=workspace, status__in=["discrepant", "unmatched"])
        .select_related("invoice", "invoice__vendor")
        .order_by("-invoice__invoice_date")
    )

    alt_fill = PatternFill("solid", fgColor=_CLR_ALT_ROW)
    for row_idx, mr in enumerate(results, start=2):
        inv = mr.invoice
        # Summarise discrepancies: join first-level "type" values
        disc_types = ", ".join(
            d.get("type", "?") for d in (mr.discrepancies or [])
        ) or mr.status

        row_data = [
            inv.invoice_number,
            inv.vendor.name,
            str(inv.invoice_date or ""),
            str(inv.due_date or ""),
            inv.currency,
            float(inv.total_amount) if inv.total_amount is not None else "",
            mr.severity,
            mr.status,
            disc_types[:120],  # cap at 120 chars so cell isn't huge
        ]
        for col_idx, value in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if row_idx % 2 == 0:
                cell.fill = alt_fill

        # Colour the Severity cell
        sev_fill = _severity_fill(mr.severity)
        if sev_fill:
            sev_cell = ws.cell(row=row_idx, column=7)
            sev_cell.fill = sev_fill
            sev_cell.font = Font(bold=True, color="FFFFFF", size=9)
            sev_cell.alignment = Alignment(horizontal="center")

    # Format amount column as currency
    for row in ws.iter_rows(min_row=2, min_col=6, max_col=6):
        for cell in row:
            if isinstance(cell.value, float):
                cell.number_format = '#,##0.00'

    _auto_width(ws)


def _sheet_contracts(wb, workspace) -> None:
    from apps.core.models import Contract

    ws = wb.create_sheet("Contracts")
    ws.sheet_view.showGridLines = False

    cols = ["Vendor", "Valid From", "Valid Until", "Status", "Days Remaining"]
    _header_row(ws, cols)

    today = timezone.now().date()
    contracts = (
        Contract.objects
        .filter(workspace=workspace, status__in=["active", "expiring", "expired"])
        .select_related("vendor")
        .order_by("valid_until")
    )

    alt_fill = PatternFill("solid", fgColor=_CLR_ALT_ROW)
    for row_idx, contract in enumerate(contracts, start=2):
        days_remaining = (
            (contract.valid_until - today).days
            if contract.valid_until else None
        )
        row_data = [
            contract.vendor.name,
            str(contract.valid_from or ""),
            str(contract.valid_until or ""),
            contract.status,
            days_remaining if days_remaining is not None else "N/A",
        ]
        for col_idx, value in enumerate(row_data, start=1):
            cell = ws.cell(row=row_idx, column=col_idx, value=value)
            if row_idx % 2 == 0:
                cell.fill = alt_fill

        # Colour status cell
        status_colours = {
            "expired":  (_CLR_CRITICAL, "FFFFFF"),
            "expiring": (_CLR_MAJOR,    "FFFFFF"),
            "active":   (_CLR_MATCHED,  "FFFFFF"),
        }
        if contract.status in status_colours:
            bg, fg = status_colours[contract.status]
            status_cell = ws.cell(row=row_idx, column=4)
            status_cell.fill = PatternFill("solid", fgColor=bg)
            status_cell.font = Font(bold=True, color=fg, size=9)
            status_cell.alignment = Alignment(horizontal="center")

    _auto_width(ws)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_compliance_workbook(workspace, stats: dict) -> bytes | None:
    """Build an .xlsx compliance report and return it as raw bytes.

    Returns ``None`` if openpyxl is not installed (so the email task degrades
    gracefully without an import error breaking the whole report cycle).
    """
    if not _OPENPYXL_AVAILABLE:
        return None

    wb = openpyxl.Workbook()
    # Remove the default blank sheet
    if "Sheet" in wb.sheetnames:
        del wb["Sheet"]

    _sheet_summary(wb, workspace, stats)
    _sheet_discrepancies(wb, workspace)
    _sheet_contracts(wb, workspace)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
