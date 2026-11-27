"""Report downloads: GET /budgeting/reports/export/ as Excel, PDF, CSV or JSON."""
import io
import json
from datetime import date

import pytest
from openpyxl import load_workbook
from rest_framework.test import APIClient

from tests.helpers import B, add_expense, create_account, create_category, set_budget

pytestmark = pytest.mark.django_db

YEAR = date.today().year
MONTH = date.today().month
URL = B + "/reports/export/"


@pytest.fixture
def data(api, settings):
    """Two accounts, a budget, an expense (SAR), salary and a transfer this month; an older expense."""
    settings.EXCHANGE_RATES = {"USD": 1.0, "SAR": 0.25}
    bank = create_account(api, "Bank")
    card = create_account(api, "Card")
    _, cat = create_category(api, "Food", "Groceries")
    set_budget(api, cat, 400)
    today = date.today()
    add_expense(api, card, cat, 200, description="Carrefour", currency="SAR")  # 50 USD
    api.post(B + "/transactions/", {"date": today.isoformat(), "direction": "income", "description": "Salary",
                                    "amount": "1000", "account_id": bank}, format="json")
    api.post(B + "/transactions/", {"date": today.isoformat(), "direction": "transfer", "description": "Card payment",
                                    "amount": "50", "account_id": bank, "to_account_id": card}, format="json")
    other_month = date(YEAR, 1 if MONTH != 1 else 2, 5)
    add_expense(api, card, cat, 30, d=other_month, description="Old shop")
    return {"api": api}


def _get(api, **params):
    params.setdefault("scope", "month")
    params.setdefault("year", YEAR)
    params.setdefault("month", MONTH)
    params.setdefault("report_currency", "USD")
    return api.get(URL, params)


def test_excel_has_transactions_on_their_own_sheet(data):
    r = _get(data["api"], type="xlsx", transactions="1")
    assert r.status_code == 200
    assert r["Content-Type"].startswith("application/vnd.openxmlformats")
    assert f'finance-report-{YEAR}-{MONTH:02d}.xlsx' in r["Content-Disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Summary", "Categories", "Spending", "Transactions"]

    ws = wb["Transactions"]
    header = [c.value for c in ws[1]]
    assert header[:3] == ["Date", "Time", "Description"] and "Amount (USD)" in header
    rows = [dict(zip(header, (c.value for c in row))) for row in ws.iter_rows(min_row=2)]
    assert sorted(r["Description"] for r in rows) == ["Card payment", "Carrefour", "Salary"]  # month only
    shop = next(r for r in rows if r["Description"] == "Carrefour")
    assert (shop["Amount"], shop["Currency"], shop["Amount (USD)"]) == (200, "SAR", 50)
    assert shop["Account"] == "Card" and "Groceries" in shop["Category"]
    transfer = next(r for r in rows if r["Description"] == "Card payment")
    assert (transfer["Type"], transfer["Account"], transfer["To account"]) == ("transfer", "Bank", "Card")


def test_excel_without_transactions_and_year_scope(data):
    wb = load_workbook(io.BytesIO(_get(data["api"], type="xlsx", scope="year").content))
    assert wb.sheetnames == ["Summary", "Months", "Spending"]
    assert wb["Months"].max_row == 13  # header + 12 months


def test_json_totals(data):
    body = json.loads(_get(data["api"], type="json", transactions="1").content)
    assert body["meta"]["currency"] == "USD" and body["meta"]["scope"] == "month"
    assert body["summary"]["income"] == "1000.00" and body["summary"]["expense"] == "50.00"
    assert body["budget"]["budget"] == "400.00"
    assert body["spending"][0]["category"] == "Food"
    assert len(body["transactions"]) == 3

    year = json.loads(_get(data["api"], type="json", scope="year").content)
    assert year["summary"]["expense"] == "80.00"  # 50 (200 SAR) this month + 30 earlier in the year
    assert "transactions" not in year


def test_csv_transactions_section_only_when_asked(data):
    without = _get(data["api"], type="csv").content.decode("utf-8-sig")
    assert "Transactions\r\n" not in without and "Carrefour" not in without
    with_txns = _get(data["api"], type="csv", transactions="1").content.decode("utf-8-sig")
    assert "Transactions" in with_txns and "Carrefour" in with_txns


def test_pdf(data):
    r = _get(data["api"], type="pdf", transactions="1")
    assert r.status_code == 200 and r["Content-Type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")


def test_only_my_transactions(data, make_user):
    stranger = APIClient()
    stranger.force_authenticate(make_user())
    body = json.loads(_get(stranger, type="json", transactions="1").content)
    assert body["transactions"] == [] and body["summary"]["expense"] == "0.00"


def test_bad_requests(api):
    assert _get(api, type="docx").status_code == 400
    assert _get(api, type="xlsx", scope="week").status_code == 400
    assert _get(api, type="xlsx", month=13).status_code == 400
    assert APIClient().get(URL, {"type": "xlsx"}).status_code in (401, 403)
