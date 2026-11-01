"""Statement import: date formats, currency, account, dedupe, encodings, XLSX, limits."""
import io
from datetime import date
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from budgeting import importer
from budgeting.store import TransactionFS
from tests.helpers import B, create_account

pytestmark = pytest.mark.django_db
URL = B + "/transactions/upload/"


def _upload(api, content, name="statement.csv", **fields):
    data = content.encode("utf-8") if isinstance(content, str) else content
    return api.post(URL, {"file": SimpleUploadedFile(name, data), **fields}, format="multipart")


def _txns(user):
    return sorted(TransactionFS.list_by_user(str(user.pk), limit=1000), key=lambda t: (t.date, t.description))


# ---- pure parsing ----

@pytest.mark.parametrize("raw,fmt,expected", [
    ("03/04/2026", "dmy", date(2026, 4, 3)),
    ("03/04/2026", "mdy", date(2026, 3, 4)),
    ("2026-04-03", "mdy", date(2026, 4, 3)),
    ("03.04.26", "dmy", date(2026, 4, 3)),
    ("13/04/2026", "auto", date(2026, 4, 13)),
    ("04/13/2026", "auto", date(2026, 4, 13)),
    ("2026/04/03", "dmy", date(2026, 4, 3)),
])
def test_parse_date(raw, fmt, expected):
    assert importer.parse_date(raw, fmt) == expected


@pytest.mark.parametrize("raw,expected", [
    ("1,234.56", "1234.56"), ("1.234,56", "1234.56"), ("(12.50)", "-12.50"),
    ("-SAR 45", "-45"), ("50-", "-50"), ("12,5", "12.5"), ("1,234", "1234"), ("ر.س 20", "20"),
])
def test_parse_amount(raw, expected):
    assert importer.parse_amount(raw) == Decimal(expected)


def test_default_date_format_by_country():
    assert importer.default_date_format("LB") == "dmy"
    assert importer.default_date_format("SA") == "dmy"
    assert importer.default_date_format("US") == "mdy"


# ---- API ----

def test_lebanese_user_gets_day_first_dates(api, user):
    api.patch("/api/v1/auth/me/", {"country": "LB"}, format="json")
    r = _upload(api, "Date,Description,Amount\n03/04/2026,Spinneys,-20\n")
    assert r.status_code == 200, r.content
    assert r.json()["date_format"] == "dmy"
    assert _txns(user)[0].date == date(2026, 4, 3)


def test_explicit_month_first(api, user):
    r = _upload(api, "Date,Description,Amount\n03/04/2026,Shop,-20\n", date_format="mdy")
    assert r.json()["date_format"] == "mdy"
    assert _txns(user)[0].date == date(2026, 3, 4)


def test_auto_detects_format_from_file(api, user):
    api.patch("/api/v1/auth/me/", {"country": "US"}, format="json")
    csv = "Date,Description,Amount\n01/02/2026,A,-1\n25/02/2026,B,-1\n"
    r = _upload(api, csv)
    assert r.json()["date_format"] == "dmy"
    assert _txns(user)[0].date == date(2026, 2, 1)


def test_currency_and_account_applied(api, user):
    acc = create_account(api, name="Al Rajhi")
    r = _upload(api, "Date,Description,Amount\n2026-04-03,Jarir,-150\n", currency="SAR", account_id=acc)
    assert r.json()["currency"] == "SAR"
    t = _txns(user)[0]
    assert t.currency == "SAR" and t.income_source_id == acc and t.source_account == "Al Rajhi"


def test_repeated_rows_import_but_reupload_does_not(api, user):
    csv = "Date,Description,Amount\n2026-04-03,Coffee,-3\n2026-04-03,Coffee,-3\n"
    assert _upload(api, csv).json()["created"] == 2
    again = _upload(api, csv).json()
    assert again["created"] == 0 and again["skipped"] == 2
    assert len(_txns(user)) == 2


def test_non_utf8_file_is_read(api, user):
    content = "Date,Description,Amount\n2026-04-03,Caf\u00e9 Beyrouth,-5\n".encode("latin-1")
    r = _upload(api, content)
    assert r.json()["created"] == 1
    assert _txns(user)[0].description == "Caf\u00e9 Beyrouth"


def test_debit_credit_columns(api, user):
    csv = "Date;Details;Debit;Credit\n2026-04-01;Salary;;5000\n2026-04-02;Rent;1200;\n"
    r = _upload(api, csv)
    assert r.json()["created"] == 2
    by_desc = {t.description: t for t in _txns(user)}
    assert by_desc["Salary"].direction == "income" and by_desc["Salary"].amount == Decimal("5000")
    assert by_desc["Rent"].direction == "expense" and by_desc["Rent"].amount == Decimal("1200")


def test_xlsx_import(api, user):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(["Date", "Description", "Amount"])
    ws.append([date(2026, 4, 3), "Panda", -42.5])
    buf = io.BytesIO()
    wb.save(buf)
    r = _upload(api, buf.getvalue(), name="statement.xlsx")
    assert r.status_code == 200, r.content
    t = _txns(user)[0]
    assert t.date == date(2026, 4, 3) and t.amount == Decimal("42.5")


def test_bad_rows_are_reported(api, user):
    r = _upload(api, "Date,Description,Amount\nnot-a-date,Shop,-1\n2026-04-03,Ok,-2\n")
    body = r.json()
    assert body["created"] == 1 and body["skipped"] == 1
    assert body["errors"][0]["row"] == 2


def test_rejects_wrong_type_and_oversize(api, settings):
    assert _upload(api, "x", name="statement.pdf").status_code == 400
    settings.TRANSACTION_IMPORT_MAX_BYTES = 10
    assert _upload(api, "Date,Description,Amount\n2026-04-03,Shop,-1\n").status_code == 400


def test_rejects_unknown_currency_and_format(api):
    csv = "Date,Description,Amount\n2026-04-03,Shop,-1\n"
    assert _upload(api, csv, currency="XYZ").status_code == 400
    assert _upload(api, csv, date_format="yyyy").status_code == 400
