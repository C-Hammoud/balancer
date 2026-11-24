"""Income vs expenses over all accounts (dashboard widget): GET /budgeting/totals/."""
from datetime import date

import pytest
from rest_framework.test import APIClient

from budgeting.balances import income_expense_totals
from tests.helpers import B, create_account, create_category

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 24)


def _post(api, **payload):
    payload.setdefault("date", TODAY.isoformat())
    r = api.post(B + "/transactions/", payload, format="json")
    assert r.status_code == 201, r.content
    return r.json()


@pytest.fixture
def setup(api):
    """Salary on an income card, spending on a credit card, and the card paid from the income card."""
    income_card = create_account(api, "Salary card")
    credit_card = create_account(api, "Credit card")
    _, cat = create_category(api)
    return {"api": api, "income": income_card, "card": credit_card, "cat": cat}


def _expense(s, amount, **extra):
    extra.setdefault("account_id", s["card"])
    return _post(s["api"], direction="expense", description=extra.pop("description", "Shop"),
                 amount=str(amount), category_id=s["cat"], **extra)


def _income(s, amount, **extra):
    extra.setdefault("account_id", s["income"])
    return _post(s["api"], direction="income", description=extra.pop("description", "Salary"),
                 amount=str(amount), **extra)


def test_periods_and_transfers(setup, user):
    s = setup
    _income(s, 1000)                                        # this month
    _expense(s, 300)                                        # this month, credit card
    _expense(s, 50, account_id=s["income"])                 # this month, other account
    _post(s["api"], direction="transfer", description="Card payment", amount="350",
          account_id=s["income"], to_account_id=s["card"])  # moving own money: ignored
    _income(s, 2000, date="2026-03-05")                     # earlier this year
    _expense(s, 400, date="2026-03-06")
    _income(s, 500, date="2025-06-01")                      # last year
    _expense(s, 100, date="2025-06-02")

    t = income_expense_totals(user, "USD", today=TODAY)
    assert t["month"] == {"income": 1000, "expense": 350, "net": 650}
    assert t["year"] == {"income": 3000, "expense": 750, "net": 2250}
    assert t["all_time"]["income"] == 3500 and t["all_time"]["expense"] == 850
    assert t["all_time"]["net"] == 2650
    assert t["all_time"]["since"] == "2025-06-01"


def test_pending_income_waits_pending_expense_counts(setup, user):
    _income(setup, 800, status="pending")
    _expense(setup, 120, status="pending")
    t = income_expense_totals(user, "USD", today=TODAY)
    assert t["month"] == {"income": 0, "expense": 120, "net": -120}


def test_converts_to_main_currency(setup, user, settings):
    settings.EXCHANGE_RATES = {"USD": 1.0, "SAR": 0.25}  # USD per 1 SAR
    _income(setup, 100, currency="USD")
    _expense(setup, 100, currency="SAR")
    t = income_expense_totals(user, "USD", today=TODAY)
    assert t["month"] == {"income": 100, "expense": 25, "net": 75}


def test_endpoint_only_counts_my_data(setup, make_user, client_for):
    _income(setup, 1000, date=date.today().isoformat())
    _expense(setup, 250, date=date.today().isoformat())
    other = client_for(make_user())
    acc = create_account(other, "Theirs")
    other.post(B + "/transactions/", {"date": date.today().isoformat(), "direction": "income",
                                       "description": "Theirs", "amount": "999", "account_id": acc}, format="json")

    body = setup["api"].get(B + "/totals/", {"report_currency": "USD"}).json()
    assert body["currency"] == "USD"
    assert body["month"] == {"income": "1000.00", "expense": "250.00", "net": "750.00"}
    assert body["all_time"]["since"] == date.today().isoformat()


def test_no_transactions(api):
    body = api.get(B + "/totals/").json()
    assert body["all_time"]["since"] is None and body["month"]["net"] == "0.00"


def test_requires_sign_in():
    assert APIClient().get(B + "/totals/").status_code == 401
