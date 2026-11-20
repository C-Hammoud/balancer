"""
Downloadable starting files for the transaction import (Transactions → Import statement).
Each template has the column headers the importer recognises (importer.HEADER_ALIASES) and two
example rows, one expense and one income, so it imports as-is and shows the expected formats.
Pure functions (no store access), like importer.py.
"""
import csv
import io
import json
from datetime import date, timedelta
from decimal import Decimal

TEMPLATE_KINDS = ("csv", "csv-debit-credit", "xlsx", "json")

CSV_TYPE = "text/csv; charset=utf-8"
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
JSON_TYPE = "application/json"

FILENAMES = {
    "csv": "transactions-template.csv",
    "csv-debit-credit": "transactions-template-debit-credit.csv",
    "xlsx": "transactions-template.xlsx",
    "json": "transactions-template.json",
}

HOW_TO_FILL = (
    "How to fill this template",
    "",
    "1. Replace the two example rows on the Transactions sheet with your own (or delete them).",
    "2. Date: one per row, best as YYYY-MM-DD (e.g. 2026-11-21). Day-first and month-first dates work too:",
    "   choose the date format in the import dialog.",
    "3. Description: the merchant or what the money was for.",
    "4. Debit: money out (an expense). Credit: money in (income). Fill one of the two per row.",
    "5. One currency per file: choose it in the import dialog (Statement currency).",
    "6. Keep the column headers in the first row. Only the first sheet is imported.",
)


class UnknownTemplate(ValueError):
    pass


def _examples(today: date) -> list[tuple[date, str, Decimal]]:
    """(date, description, signed amount): negative is money out, positive is money in."""
    return [
        (today - timedelta(days=1), "Supermarket", Decimal("-45.50")),
        (today - timedelta(days=2), "Salary", Decimal("5000.00")),
    ]


def _csv_bytes(rows: list[list[str]]) -> bytes:
    out = io.StringIO()
    csv.writer(out, lineterminator="\r\n").writerows(rows)
    # BOM so Excel opens it as UTF-8; the importer decodes with utf-8-sig.
    return out.getvalue().encode("utf-8-sig")


def _money(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _csv_amount(today: date) -> bytes:
    rows = [["Date", "Description", "Amount"]]
    rows += [[d.isoformat(), desc, _money(amt)] for d, desc, amt in _examples(today)]
    return _csv_bytes(rows)


def _csv_debit_credit(today: date) -> bytes:
    rows = [["Date", "Description", "Debit", "Credit"]]
    for d, desc, amt in _examples(today):
        debit, credit = (_money(-amt), "") if amt < 0 else ("", _money(amt))
        rows.append([d.isoformat(), desc, debit, credit])
    return _csv_bytes(rows)


def _xlsx(today: date) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    wb = Workbook()
    ws = wb.active
    ws.title = "Transactions"
    ws.append(["Date", "Description", "Debit", "Credit"])
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for d, desc, amt in _examples(today):
        debit, credit = (float(-amt), None) if amt < 0 else (None, float(amt))
        ws.append([d, desc, debit, credit])
    for row in ws.iter_rows(min_row=2):
        row[0].number_format = "yyyy-mm-dd"
        for cell in row[2:4]:
            cell.number_format = "#,##0.00"
    for col, width in zip("ABCD", (12, 32, 12, 12)):
        ws.column_dimensions[col].width = width
    ws.freeze_panes = "A2"

    guide = wb.create_sheet("How to fill")
    for line in HOW_TO_FILL:
        guide.append([line])
    guide["A1"].font = Font(bold=True)
    guide.column_dimensions["A"].width = 100

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _json(today: date) -> bytes:
    data = {
        "transactions": [
            {"date": d.isoformat(), "description": desc, "amount": float(amt)}
            for d, desc, amt in _examples(today)
        ]
    }
    return (json.dumps(data, indent=2) + "\n").encode("utf-8")


_BUILDERS = {
    "csv": (_csv_amount, CSV_TYPE),
    "csv-debit-credit": (_csv_debit_credit, CSV_TYPE),
    "xlsx": (_xlsx, XLSX_TYPE),
    "json": (_json, JSON_TYPE),
}


def build_template(kind: str, today: date) -> tuple[bytes, str, str]:
    """(content, content type, filename) for one of TEMPLATE_KINDS; UnknownTemplate otherwise."""
    if kind not in _BUILDERS:
        raise UnknownTemplate(kind)
    builder, content_type = _BUILDERS[kind]
    return builder(today), content_type, FILENAMES[kind]
