"""
Changing the main currency converts saved amounts (budgets, net worth) instead of relabelling them.
Rates: 1 SAR = 0.25 USD.
"""
from datetime import date
from decimal import Decimal

import pytest
from django.core.management import call_command

from api.user_preferences import save_user_preferences
from budgeting.store import BudgetAlertFS, BudgetFS, FinancialStandingFS, SavingsFS
from tests.helpers import B, add_expense, create_account, create_category, set_budget

pytestmark = pytest.mark.django_db

TODAY = date.today()


@pytest.fixture
def sar_user(user, api, settings):
    """Main currency SAR, a 1,500 SAR Groceries budget and 750 SAR spent (50%)."""
    settings.EXCHANGE_RATES = {"USD": 1.0, "SAR": 0.25}
    save_user_preferences(user, {"default_currency": "SAR"})
    account = create_account(api)
    group_id, cat = create_category(api)
    set_budget(api, cat, 1500)
    add_expense(api, account, cat, 750, currency="SAR")
    return {"api": api, "cat": cat, "group": group_id, "account": account}


def _switch(api, code):
    r = api.patch("/api/v1/auth/me/", {"default_currency": code}, format="json")
    assert r.status_code == 200, r.content


def _row(report, cat):
    return next(r for r in report["rows"] if r["category_id"] == cat)


def test_utilization_converts_budgets_with_spending(sar_user):
    api, cat = sar_user["api"], sar_user["cat"]
    before = _row(api.get(B + "/utilization/").json(), cat)
    assert (before["forecast"], before["actual"], before["utilization_pct"]) == ("1500.00", "750.00", "50.0")

    _switch(api, "USD")
    body = api.get(B + "/utilization/").json()
    after = _row(body, cat)
    assert body["report_currency"] == "USD"
    assert (after["forecast"], after["actual"], after["utilization_pct"]) == ("375.00", "187.50", "50.0")


def test_budget_list_and_yearly_agree(sar_user):
    api, cat = sar_user["api"], sar_user["cat"]
    _switch(api, "USD")
    body = api.get(B + "/budgets/", {"year": TODAY.year, "month": TODAY.month}).json()
    assert body["report_currency"] == "USD"
    row = next(r for r in body["rows"] if r["group_id"] == sar_user["group"])
    sub = row["sub_budgets"][0]
    assert (sub["forecast"], sub["actual"]) == ("375.00", "187.50")

    year = api.get(B + "/yearly/", {"year": TODAY.year}).json()
    month = year["months"][TODAY.month - 1]
    assert Decimal(month["total_forecast"]) == Decimal("375") and Decimal(month["total_actual"]) == Decimal("187.5")


def test_edit_in_new_currency_then_switch_back(sar_user, user):
    api, cat = sar_user["api"], sar_user["cat"]
    _switch(api, "USD")
    set_budget(api, cat, 400)  # typed in USD
    saved = BudgetFS.get_by_user_category_month(str(user.pk), cat, TODAY.year, TODAY.month)
    assert (saved.forecast, saved.currency) == (Decimal("400"), "USD")

    _switch(api, "SAR")
    assert _row(api.get(B + "/utilization/").json(), cat)["forecast"] == "1600.00"


def test_old_rows_keep_their_currency_on_switch(user, api, settings):
    """Rows saved before currencies were recorded are stamped with the old main currency."""
    settings.EXCHANGE_RATES = {"USD": 1.0, "SAR": 0.25}
    save_user_preferences(user, {"default_currency": "SAR"})
    _, cat = create_category(api)
    uid = str(user.pk)
    BudgetFS(user_id=uid, category_id=cat, year=TODAY.year, month=TODAY.month, forecast=Decimal("1000")).save()
    SavingsFS(user_id=uid, year=TODAY.year, month=TODAY.month, target=Decimal("200")).save()

    save_user_preferences(user, {"default_currency": "USD"})
    assert BudgetFS.list_by_user(uid)[0].currency == "SAR"
    assert SavingsFS.list_by_user(uid)[0].currency == "SAR"
    assert _row(api.get(B + "/utilization/").json(), cat)["forecast"] == "250.00"


def test_alerts_quote_one_currency(sar_user, user):
    api = sar_user["api"]
    add_expense(api, sar_user["account"], sar_user["cat"], 600, currency="SAR")  # 1,350 of 1,500: warn
    _switch(api, "USD")  # refreshes this month's alerts
    alerts = [a for a in BudgetAlertFS.list_by_user(str(user.pk), open_only=False)
              if a.category_id == sar_user["cat"]]
    assert alerts and all(a.forecast == Decimal("375.00") for a in alerts)
    assert "USD" in alerts[0].description


def test_net_worth_is_converted(sar_user):
    api = sar_user["api"]
    r = api.post(B + "/financial-standing/", {"snapshot_date": TODAY.isoformat(), "total_assets": "1000",
                                               "total_liabilities": "400"}, format="json")
    assert r.status_code == 201, r.content
    _switch(api, "USD")
    s = api.get(B + "/financial-standing/").json()[0]
    assert (s["currency"], s["total_assets"], s["total_liabilities"]) == ("USD", "250.00", "100.00")


def test_stamp_command_fills_blanks_only(user, api):
    _, cat = create_category(api)
    uid = str(user.pk)
    BudgetFS(user_id=uid, category_id=cat, year=2026, month=1, forecast=Decimal("10")).save()
    BudgetFS(user_id=uid, category_id=cat, year=2026, month=2, forecast=Decimal("20"), currency="USD").save()
    FinancialStandingFS(user_id=uid, snapshot_date=TODAY, total_assets=Decimal("5")).save()

    call_command("stamp_money_currency", currency="SAR", dry_run=True)
    assert sorted(b.currency for b in BudgetFS.list_by_user(uid)) == ["", "USD"]

    call_command("stamp_money_currency", currency="SAR")
    rows = {b.month: b for b in BudgetFS.list_by_user(uid)}
    assert (rows[1].currency, rows[1].forecast) == ("SAR", Decimal("10"))
    assert rows[2].currency == "USD"
    assert FinancialStandingFS.list_by_user(uid)[0].currency == "SAR"

    call_command("stamp_money_currency", currency="SAR")  # safe to run twice
    assert sorted(b.currency for b in BudgetFS.list_by_user(uid)) == ["SAR", "USD"]


def test_stamp_command_rejects_unknown_currency():
    from django.core.management.base import CommandError

    with pytest.raises(CommandError):
        call_command("stamp_money_currency", currency="XYZ")
