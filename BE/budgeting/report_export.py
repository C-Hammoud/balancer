"""
Downloadable reports (dashboard / Reports page): a year or a month as Excel, PDF, CSV or JSON.

build_report() gathers the figures once (in the main currency, like the rest of the app);
each writer turns that dict into a file. Transactions are optional and cover the same period:
in Excel they get their own sheet.
"""
from __future__ import annotations

import csv
import io
import json
from calendar import month_name
from datetime import date, datetime
from decimal import Decimal

from api.currency import convert_if_needed

from .services import (
    actual_expense_total,
    actual_income_total,
    budget_utilization_report,
    categories_and_groups_for_user,
    yearly_overview_report,
)
from .store import IncomeSourceFS, TransactionFS

FORMATS = ("xlsx", "pdf", "csv", "json")
SCOPES = ("year", "month")
ZERO = Decimal("0")

CONTENT_TYPES = {
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
    "csv": "text/csv; charset=utf-8",
    "json": "application/json",
}

TRANSACTION_COLUMNS = (
    ("date", "Date"),
    ("time", "Time"),
    ("description", "Description"),
    ("type", "Type"),
    ("status", "Status"),
    ("category", "Category"),
    ("account", "Account"),
    ("to_account", "To account"),
    ("amount", "Amount"),
    ("currency", "Currency"),
    ("amount_main", "Amount ({cur})"),
    ("note", "Note"),
)


class ReportError(ValueError):
    """Bad format / scope / period (shown to the user as a 400)."""


def _dec(v) -> Decimal:
    """Money value rounded to cents (0 for empty or bad input)."""
    try:
        return Decimal(str(v if v is not None else 0)).quantize(Decimal("0.01"))
    except Exception:
        return Decimal("0.00")


def _period_label(scope: str, year: int, month: int) -> str:
    return str(year) if scope == "year" else f"{month_name[month]} {year}"


def filename_for(scope: str, year: int, month: int, fmt: str) -> str:
    stem = f"finance-report-{year}" if scope == "year" else f"finance-report-{year}-{month:02d}"
    return f"{stem}.{fmt}"


def _in_period(t, scope: str, year: int, month: int) -> bool:
    d = getattr(t, "date", None)
    if not d:
        return False
    return d.year == year and (scope == "year" or d.month == month)


def _transactions(user, scope, year, month, currency, categories_by_id) -> tuple[list[dict], list[dict]]:
    """(transaction rows, spending by parent category) for the period, amounts converted."""
    uid = str(user.pk)
    accounts = {a.pk: a.name for a in IncomeSourceFS.list_by_user(uid, limit=1000)}
    rows, spending = [], {}
    txns = [t for t in TransactionFS.list_all_for_user(uid) if _in_period(t, scope, year, month)]
    txns.sort(key=lambda t: (t.date, getattr(t, "time", "") or "", t.pk or ""))
    for t in txns:
        cat = categories_by_id.get(t.category_id) if t.category_id else None
        group = (getattr(cat, "group_name", "") or "") if cat else ""
        category = f"{group} · {cat.name}" if cat and group and group != cat.name else (cat.name if cat else "")
        amount = _dec(t.amount)
        main = convert_if_needed(amount, t.currency or "USD", currency)
        rows.append({
            "date": t.date,
            "time": getattr(t, "time", "") or "",
            "description": t.description or "",
            "type": t.direction or "",
            "status": getattr(t, "status", "") or "settled",
            "category": category,
            "account": accounts.get(getattr(t, "income_source_id", "") or "", ""),
            "to_account": accounts.get(getattr(t, "to_account_id", "") or "", ""),
            "amount": amount,
            "currency": (t.currency or "USD").upper(),
            "amount_main": main,
            "note": getattr(t, "note", "") or "",
        })
        if t.direction == "expense":
            key = group or (cat.name if cat else "Uncategorized")
            spending[key] = spending.get(key, ZERO) + _dec(main)
    total = sum(spending.values(), ZERO)
    spend_rows = [
        {"category": k, "amount": v, "percent": (v / total * 100).quantize(Decimal("0.1")) if total else ZERO}
        for k, v in sorted(spending.items(), key=lambda kv: kv[1], reverse=True)
    ]
    return rows, spend_rows


def build_report(user, scope: str, year: int, month: int, currency: str, include_transactions: bool) -> dict:
    if scope not in SCOPES:
        raise ReportError(f"Unknown scope. Use one of: {', '.join(SCOPES)}.")
    if not (1900 <= year <= 2200) or not (1 <= month <= 12):
        raise ReportError("Choose a valid year and month.")

    _, categories_by_id = categories_and_groups_for_user(user)
    data: dict = {
        "meta": {
            "title": f"Finance report — {_period_label(scope, year, month)}",
            "scope": scope,
            "year": year,
            "month": month if scope == "month" else None,
            "period": _period_label(scope, year, month),
            "currency": currency,
            "generated_at": datetime.now().replace(microsecond=0).isoformat(),
        }
    }

    if scope == "year":
        y = yearly_overview_report(user, year, report_currency=currency)
        income, expense = _dec(y["income_total"]), _dec(y["expense_total"])
        data["months"] = [
            {
                "month": month_name[m["month"]],
                "income": _dec(m["income_total"]),
                "expense": _dec(m["expense_total"]),
                "net": _dec(m["net"]),
                "budget": _dec(m.get("total_forecast")),
                "budget_used_pct": m.get("overall_util"),
                "budget_left": _dec(m.get("remaining")),
            }
            for m in y["months"]
        ]
    else:
        income = _dec(actual_income_total(user, year, month, report_currency=currency))
        expense = _dec(actual_expense_total(user, year, month, report_currency=currency))
        util = budget_utilization_report(user, year, month, report_currency=currency)
        data["categories"] = [
            {
                "category": r["category_name"],
                "level": "subcategory" if r.get("row_type") == "subcategory" else "category",
                "budget": _dec(r["forecast"]),
                "spent": _dec(r["actual"]),
                "left": _dec(r["remaining"]),
                "used_pct": r.get("utilization_pct"),
                "status": r.get("status") or "",
            }
            for r in util["rows"]
        ]
        data["budget"] = {
            "budget": _dec(util["total_forecast"]),
            "spent": _dec(util["total_actual"]),
            "left": _dec(util["remaining"]),
            "used_pct": util.get("overall_util"),
        }

    net = income - expense
    data["summary"] = {
        "income": income,
        "expense": expense,
        "net": net,
        "savings_rate_pct": (net / income * 100).quantize(Decimal("0.1")) if income > 0 else None,
    }
    txn_rows, spending = _transactions(user, scope, year, month, currency, categories_by_id)
    data["spending"] = spending
    if include_transactions:
        data["transactions"] = txn_rows
    return data


# ---- Writers ----------------------------------------------------------------------------


def _summary_rows(data: dict) -> list[tuple[str, object]]:
    s, cur = data["summary"], data["meta"]["currency"]
    rows = [
        ("Period", data["meta"]["period"]),
        ("Currency", cur),
        ("Income", s["income"]),
        ("Expenses", s["expense"]),
        ("Net", s["net"]),
        ("Savings rate %", s["savings_rate_pct"]),
    ]
    if "budget" in data:
        b = data["budget"]
        rows += [("Budget", b["budget"]), ("Spent of budget", b["spent"]),
                 ("Budget left", b["left"]), ("Budget used %", b["used_pct"])]
    if "transactions" in data:
        rows.append(("Transactions", len(data["transactions"])))
    rows.append(("Generated", data["meta"]["generated_at"].replace("T", " ")))
    return rows


def _detail_table(data: dict) -> tuple[str, list[str], list[str], list[dict]]:
    """(sheet title, headers, keys, rows) for the months (year) or categories (month) table."""
    if "months" in data:
        return ("Months", ["Month", "Income", "Expenses", "Net", "Budget", "Budget used %", "Budget left"],
                ["month", "income", "expense", "net", "budget", "budget_used_pct", "budget_left"], data["months"])
    return ("Categories", ["Category", "Budget", "Spent", "Left", "Used %", "Status"],
            ["category", "budget", "spent", "left", "used_pct", "status"],
            [dict(r, category=("   " + r["category"]) if r["level"] == "subcategory" else r["category"])
             for r in data["categories"]])


def _txn_headers(data: dict) -> list[str]:
    cur = data["meta"]["currency"]
    return [label.format(cur=cur) for _, label in TRANSACTION_COLUMNS]


def to_json(data: dict) -> bytes:
    def default(o):
        if isinstance(o, Decimal):
            return str(o)
        if isinstance(o, (date, datetime)):
            return o.isoformat()
        raise TypeError(type(o))

    return json.dumps(data, default=default, ensure_ascii=False, indent=2).encode("utf-8")


def to_csv(data: dict) -> bytes:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow([data["meta"]["title"]])
    for label, value in _summary_rows(data):
        w.writerow([label, "" if value is None else value])
    title, headers, keys, rows = _detail_table(data)
    w.writerow([])
    w.writerow([title])
    w.writerow(headers)
    for r in rows:
        w.writerow(["" if r[k] is None else r[k] for k in keys])
    if data["spending"]:
        w.writerow([])
        w.writerow(["Spending by category"])
        w.writerow(["Category", f"Amount ({data['meta']['currency']})", "Percent"])
        for r in data["spending"]:
            w.writerow([r["category"], r["amount"], r["percent"]])
    if "transactions" in data:
        w.writerow([])
        w.writerow(["Transactions"])
        w.writerow(_txn_headers(data))
        for t in data["transactions"]:
            w.writerow([t[k].isoformat() if k == "date" else t[k] for k, _ in TRANSACTION_COLUMNS])
    # BOM so Excel opens accented / Arabic text correctly.
    return ("﻿" + out.getvalue()).encode("utf-8")


MONEY_KEYS = {"income", "expense", "net", "budget", "budget_left", "spent", "left", "amount", "amount_main"}
PCT_KEYS = {"budget_used_pct", "used_pct", "percent"}


def _num(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return v


def to_xlsx(data: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    head_font = Font(bold=True, color="FFFFFF")
    head_fill = PatternFill("solid", fgColor="0F3D3E")

    def table(ws, headers, rows, keys, widths=None):
        ws.append(headers)
        for cell in ws[ws.max_row]:
            cell.font, cell.fill = head_font, head_fill
            cell.alignment = Alignment(vertical="center")
        first = ws.max_row
        for r in rows:
            ws.append([r[k] if k == "date" else (_num(r[k]) if k in MONEY_KEYS | PCT_KEYS else r[k]) for k in keys])
        for row in ws.iter_rows(min_row=first + 1):
            for key, cell in zip(keys, row):
                if key in MONEY_KEYS:
                    cell.number_format = "#,##0.00"
                elif key in PCT_KEYS:
                    cell.number_format = "0.0"
                elif key == "date":
                    cell.number_format = "yyyy-mm-dd"
        ws.freeze_panes = ws.cell(row=first + 1, column=1)
        if rows:
            ws.auto_filter.ref = f"A{first}:{get_column_letter(len(keys))}{ws.max_row}"
        for i, w in enumerate(widths or [], start=1):
            ws.column_dimensions[get_column_letter(i)].width = w

    wb = Workbook()
    ws = wb.active
    ws.title = "Summary"
    ws.append([data["meta"]["title"]])
    ws["A1"].font = Font(bold=True, size=14, color="0F3D3E")
    ws.append([])
    for label, value in _summary_rows(data):
        ws.append([label, _num(value) if label not in ("Period", "Currency", "Generated") else value])
        cell = ws.cell(row=ws.max_row, column=2)
        if label.endswith("%"):
            cell.number_format = "0.0"
        elif label not in ("Period", "Currency", "Generated", "Transactions"):
            cell.number_format = "#,##0.00"
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 24

    title, headers, keys, rows = _detail_table(data)
    table(wb.create_sheet(title), headers, rows, keys, [24] + [14] * (len(keys) - 1))

    table(wb.create_sheet("Spending"), ["Category", f"Amount ({data['meta']['currency']})", "Percent"],
          data["spending"], ["category", "amount", "percent"], [28, 16, 10])

    if "transactions" in data:
        table(wb.create_sheet("Transactions"), _txn_headers(data), data["transactions"],
              [k for k, _ in TRANSACTION_COLUMNS], [12, 7, 36, 9, 9, 26, 18, 18, 13, 9, 15, 28])

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def to_pdf(data: dict) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    teal = colors.HexColor("#0F3D3E")
    styles = getSampleStyleSheet()
    cell = styles["BodyText"].clone("cell", fontSize=7.5, leading=9)
    h1 = styles["Title"].clone("h1", textColor=teal, alignment=0, fontSize=18)
    h2 = styles["Heading2"].clone("h2", textColor=teal, spaceBefore=10, keepWithNext=True)

    def fmt(key, v):
        if v is None or v == "":
            return ""
        if key in MONEY_KEYS:
            return f"{_dec(v):,.2f}"
        if key in PCT_KEYS:
            return f"{_dec(v):.1f}%"
        if isinstance(v, date):
            return v.isoformat()
        return str(v)

    def grid(headers, body, widths=None, right_cols=None):
        right_cols = range(1, len(headers)) if right_cols is None else right_cols
        t = Table([headers] + body, colWidths=widths, repeatRows=1, hAlign="LEFT")
        t.setStyle(TableStyle([
            *[("ALIGN", (c, 1), (c, -1), "RIGHT") for c in right_cols],
            ("BACKGROUND", (0, 0), (-1, 0), teal),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F1F6F5")]),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#D5E0DF")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        return t

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(colors.grey)
        canvas.drawString(doc.leftMargin, 8 * mm, data["meta"]["title"])
        canvas.drawRightString(doc.pagesize[0] - doc.rightMargin, 8 * mm, f"Page {doc.page}")
        canvas.restoreState()

    with_txns = "transactions" in data
    page = landscape(A4) if with_txns else A4
    out = io.BytesIO()
    doc = SimpleDocTemplate(out, pagesize=page, leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=14 * mm, bottomMargin=16 * mm, title=data["meta"]["title"])
    story = [Paragraph(data["meta"]["title"], h1),
             Paragraph(f"Amounts in {data['meta']['currency']}", styles["Normal"]), Spacer(1, 6)]

    summary = [[label, fmt("percent" if label.endswith("%") else ("x" if label in ("Period", "Currency", "Generated", "Transactions") else "amount"), value)]
               for label, value in _summary_rows(data)]
    story += [grid(["Summary", ""], summary, [60 * mm, 50 * mm])]

    title, headers, keys, rows = _detail_table(data)
    story += [Paragraph(title, h2), grid(headers, [[fmt(k, r[k]) for k in keys] for r in rows])]

    if data["spending"]:
        story += [Paragraph("Spending by category", h2),
                  grid(["Category", f"Amount ({data['meta']['currency']})", "Percent"],
                       [[r["category"], fmt("amount", r["amount"]), fmt("percent", r["percent"])] for r in data["spending"]],
                       [80 * mm, 40 * mm, 25 * mm])]

    if with_txns:
        keys = [k for k, _ in TRANSACTION_COLUMNS]
        body = [[Paragraph(fmt(k, t[k]).replace("&", "&amp;").replace("<", "&lt;"), cell)
                 if k in ("description", "category", "note") else fmt(k, t[k]) for k in keys]
                for t in data["transactions"]]
        widths = [18, 10, 50, 15, 14, 36, 24, 22, 20, 15, 25, 0]
        # The frame keeps 6 pt padding on each side: stay inside it or the table jumps a page.
        usable = (doc.width - 12) / mm
        widths[-1] = max(usable - sum(widths[:-1]), 15)
        story += [Paragraph(f"Transactions ({len(body)})", h2),
                  grid(_txn_headers(data), body or [["No transactions in this period."] + [""] * (len(keys) - 1)],
                       [w * mm for w in widths], right_cols=[8, 10])]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return out.getvalue()


WRITERS = {"xlsx": to_xlsx, "pdf": to_pdf, "csv": to_csv, "json": to_json}


def export_report(user, fmt: str, scope: str, year: int, month: int, currency: str,
                  include_transactions: bool) -> tuple[bytes, str, str]:
    """(file bytes, content type, filename)."""
    if fmt not in FORMATS:
        raise ReportError(f"Unknown format. Use one of: {', '.join(FORMATS)}.")
    data = build_report(user, scope, year, month, currency, include_transactions)
    return WRITERS[fmt](data), CONTENT_TYPES[fmt], filename_for(scope, year, month, fmt)


__all__ = ["FORMATS", "SCOPES", "ReportError", "build_report", "export_report"]
