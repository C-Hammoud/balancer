"""Import templates: each download imports as-is, as one expense and one income."""
import importlib.util
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from budgeting import import_templates, importer
from budgeting.store import TransactionFS
from tests.helpers import B, create_account

pytestmark = pytest.mark.django_db

NEEDS_OPENPYXL = pytest.mark.skipif(importlib.util.find_spec("openpyxl") is None, reason="openpyxl not installed")
KINDS = ["csv", "csv-debit-credit", pytest.param("xlsx", marks=NEEDS_OPENPYXL), "json"]
TODAY = date(2026, 11, 21)


def _url(kind):
    return f"{B}/transactions/import-template/{kind}/"


def _download(api, kind):
    r = api.get(_url(kind))
    assert r.status_code == 200, getattr(r, "content", r)
    return r


@pytest.mark.parametrize("kind", KINDS)
def test_template_reads_back_as_one_expense_and_one_income(kind):
    content, _, filename = import_templates.build_template(kind, TODAY)
    rows, _ = importer.read_statement(filename, content)
    col_map = importer.column_map(rows[0])
    assert col_map is not None, rows[0]
    parsed = []
    for row in rows[1:]:
        d, desc, amount = importer.extract_fields(row, col_map)
        parsed.append((importer.parse_date(d, "auto"), desc, importer.parse_amount(amount)))
    assert parsed == [
        (TODAY - timedelta(days=1), "Supermarket", Decimal("-45.50")),
        (TODAY - timedelta(days=2), "Salary", Decimal("5000.00")),
    ]


@pytest.mark.parametrize("kind,content_type,filename", [
    ("csv", "text/csv", "transactions-template.csv"),
    ("csv-debit-credit", "text/csv", "transactions-template-debit-credit.csv"),
    pytest.param("xlsx", "spreadsheetml", "transactions-template.xlsx", marks=NEEDS_OPENPYXL),
    ("json", "application/json", "transactions-template.json"),
])
def test_download_is_an_attachment(api, kind, content_type, filename):
    r = _download(api, kind)
    assert content_type in r["Content-Type"]
    assert r["Content-Disposition"] == f'attachment; filename="{filename}"'


@pytest.mark.parametrize("kind", KINDS)
def test_downloaded_template_uploads_unchanged(api, user, kind):
    r = _download(api, kind)
    filename = import_templates.FILENAMES[kind]
    bank = create_account(api)
    up = api.post(B + "/transactions/upload/", {
        "file": SimpleUploadedFile(filename, r.content), "currency": "SAR", "account_id": bank,
    }, format="multipart")
    assert up.status_code in (200, 201), up.content
    assert up.json()["created"] == 2 and not up.json().get("errors")
    rows = {t.description: t for t in TransactionFS.list_by_user(str(user.pk), limit=100)}
    assert rows["Supermarket"].direction == "expense" and abs(Decimal(str(rows["Supermarket"].amount))) == Decimal("45.50")
    assert rows["Salary"].direction == "income" and Decimal(str(rows["Salary"].amount)) == Decimal("5000.00")
    assert {t.currency for t in rows.values()} == {"SAR"}


@NEEDS_OPENPYXL
def test_xlsx_has_a_guide_sheet_the_importer_ignores():
    from io import BytesIO

    from openpyxl import load_workbook

    content, _, _ = import_templates.build_template("xlsx", TODAY)
    wb = load_workbook(BytesIO(content))
    assert wb.sheetnames == ["Transactions", "How to fill"]
    assert [c.value for c in wb["Transactions"][1]] == ["Date", "Description", "Debit", "Credit"]


def test_unknown_template_and_anonymous_requests(api):
    r = api.get(_url("pdf"))
    assert r.status_code == 404 and "csv" in r.json()["detail"]
    assert APIClient().get(_url("csv")).status_code == 401
