"""Plan sub-budgets: reserved money in the plan, counting only in the sub-budget, default budget retired."""
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest

from budgeting import sub_budgets
from budgeting.models import PersonalBudget
from budgeting.store import PersonalBudgetFS, TransactionFS
from tests.helpers import B, add_expense, create_account, create_category, set_budget

pytestmark = pytest.mark.django_db

PB = B + "/personal-budgets/"


@pytest.fixture
def ready(api):
    api.post(B + "/income-streams/", {"name": "Salary", "amount": "4000", "currency": "USD"}, format="json")
    group, cat = create_category(api, group_name="Fun", name="Restaurants")
    return {"group": group, "cat": cat, "account": create_account(api)}


def _trip(api, **extra):
    payload = {"name": "Trip", "total_amount": "1500", "currency": "USD", "start_date": "2027-02-10",
               "end_date": "2027-02-20", **extra}
    r = api.post(PB, payload, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def _preview(api, year, month):
    body = api.post(B + "/plans/preview/", {"year": year, "month": month}, format="json").json()
    return body["plans"][0]  # 50/30/20


# ---- Funding schedule --------------------------------------------------------------

def test_split_over_months_last_month_takes_the_rest():
    b = SimpleNamespace(total_amount=Decimal("1000"), funding_months=3, funding_start=date(2026, 11, 1),
                        start_date=None, currency="USD")
    amounts = [sub_budgets.contribution_for(b, y, m, "USD") for y, m in ((2026, 11), (2026, 12), (2027, 1), (2027, 2))]
    assert amounts == [Decimal("333.33"), Decimal("333.33"), Decimal("333.34"), Decimal("0")]


def test_default_window_ends_the_month_before_the_trip():
    today = date(2026, 10, 22)
    assert sub_budgets.default_funding(SimpleNamespace(start_date=date(2027, 2, 10)), today) == (date(2026, 10, 1), 4)
    assert sub_budgets.default_funding(SimpleNamespace(start_date=date(2026, 10, 30)), today) == (date(2026, 10, 1), 1)
    assert sub_budgets.default_funding(SimpleNamespace(start_date=None), today) == (date(2026, 10, 1), 1)


# ---- Plan reserves the money -----------------------------------------------------------

def test_plan_reserves_sub_budget_and_reduces_savings(api, ready):
    before = _preview(api, 2026, 11)
    trip = _trip(api, in_plan=True, funding_start="2026-11-01", funding_months=3)
    assert trip["in_plan"] and trip["funding_months"] == 3
    plan = _preview(api, 2026, 11)
    assert plan["reserved_total"] == "500.00"
    assert [s["name"] for s in plan["sub_budgets"]] == ["Trip"]
    assert Decimal(plan["savings_amount"]) == Decimal(before["savings_amount"]) - 500
    # the group lines are unchanged
    assert [l["amount"] for l in plan["lines"]] == [l["amount"] for l in before["lines"]]
    # nothing reserved outside the funding window
    assert _preview(api, 2027, 3)["reserved_total"] == "0.00"


def test_over_reserving_warns(api, ready):
    _trip(api, total_amount="5000", in_plan=True, funding_start="2026-11-01", funding_months=1)
    plan = _preview(api, 2026, 11)
    assert Decimal(plan["savings_amount"]) < 0
    assert any("sub-budgets need" in w for w in plan["warnings"])


def test_saved_and_accepted_plan_keeps_sub_budgets(api, ready):
    trip = _trip(api, in_plan=True, funding_start="2026-11-01", funding_months=3)
    api.patch(f"{PB}{trip['id']}/", {"in_plan": False}, format="json")
    without = _preview(api, 2026, 11)["savings_amount"]
    api.patch(f"{PB}{trip['id']}/", {"in_plan": True, "funding_start": "2026-11-01", "funding_months": 3}, format="json")
    r = api.post(B + "/plans/", {"year": 2026, "month": 11, "plan_type": "rule_50_30_20"}, format="json")
    assert r.json()["reserved_total"] == "500.00"
    assert api.post("%s/plans/%s/accept/" % (B, r.json()["id"])).status_code == 200
    # the savings target is what is left after the trip's 500
    assert Decimal(api.get(B + "/savings/2026/11/").json()["target"]) == Decimal(without) - 500
    assert api.get(f"{PB}{trip['id']}/").json()["status"] == "active"  # draft -> active


# ---- Counting rule ------------------------------------------------------------------

def _utilization(api, cat):
    report = api.get(B + "/utilization/", {"year": date.today().year, "month": date.today().month}).json()
    rows = report["report"]["rows"] if "report" in report else report["rows"]
    return next((r for r in rows if r["category_id"] == cat), None)


def test_sub_budget_expenses_count_only_in_the_sub_budget(api, ready):
    set_budget(api, ready["cat"], 100)
    trip = _trip(api)
    add_expense(api, ready["account"], ready["cat"], 90, budget_id=trip["id"])
    # standalone budget: the expense still counts in Restaurants
    assert Decimal(_utilization(api, ready["cat"])["actual"]) == 90

    r = api.patch(f"{PB}{trip['id']}/", {"in_plan": True}, format="json")
    assert r.status_code == 200 and r.json()["in_plan"] and r.json()["transactions_count"] == 1
    row = _utilization(api, ready["cat"])
    assert row is None or Decimal(row["actual"]) == 0
    assert api.get(f"{PB}{trip['id']}/").json()["spent"] == "90.00"  # still counted in the trip

    api.patch(f"{PB}{trip['id']}/", {"in_plan": False}, format="json")
    assert Decimal(_utilization(api, ready["cat"])["actual"]) == 90


def test_spending_history_ignores_sub_budget_expenses(api, ready, user):
    from budgeting.planning import spending_by_group

    trip = _trip(api, in_plan=True)
    last_month = date.today().replace(day=1) - timedelta(days=1)
    add_expense(api, ready["account"], ready["cat"], 200, d=last_month, budget_id=trip["id"])
    add_expense(api, ready["account"], ready["cat"], 50, d=last_month)
    history, _ = spending_by_group(user, date.today().year, date.today().month, "USD")
    assert history[ready["group"]] == Decimal("50")


# ---- Rules ------------------------------------------------------------------------

def test_cannot_attach_someone_elses_or_archived_budget(api, ready, make_user, client_for):
    trip = _trip(api)
    other = client_for(make_user())
    assert other.patch(f"{PB}{trip['id']}/", {"in_plan": True}, format="json").status_code in (400, 403, 404)
    archived = _trip(api, name="Old", status="archived")
    r = api.patch(f"{PB}{archived['id']}/", {"in_plan": True}, format="json")
    assert r.status_code == 400
    assert PersonalBudget.objects.get(pk=archived["id"]).in_plan is False
    assert api.patch(f"{PB}{trip['id']}/", {"in_plan": True, "funding_months": "many"}, format="json").status_code == 400


def test_filter_by_in_plan(api, ready):
    _trip(api, in_plan=True)
    _trip(api, name="Laptop")
    names = lambda flag: [b["name"] for b in api.get(PB, {"in_plan": flag}).json()["budgets"]]  # noqa: E731
    assert names("1") == ["Trip"]
    assert names("0") == ["Laptop"]


def test_default_budget_is_retired_once(api, ready, user):
    default = PersonalBudgetFS(user_id=str(user.pk), name="Monthly Expenses", status="active", is_default=True).save()
    t = add_expense(api, ready["account"], ready["cat"], 10, budget_id=default.pk)
    api.get(PB)
    retired = PersonalBudget.objects.get(pk=default.pk)
    assert retired.status == "archived" and retired.is_default is False
    assert TransactionFS.get(t["id"]).budget_id == ""
    api.get(PB)  # idempotent, and no new default is created
    assert PersonalBudget.objects.filter(user=user, is_default=True).count() == 0


def test_risk_sees_an_upcoming_trip_this_month(api, ready, user):
    from budgeting.risk import build_report

    today = date.today()
    _trip(api, total_amount="700", in_plan=True, start_date=today.isoformat(), end_date=today.isoformat())
    api.post(B + "/transactions/", {"date": today.isoformat(), "direction": "income", "description": "Salary",
                                   "amount": "3000", "account_id": ready["account"]}, format="json")
    report = build_report(user, "USD", save_snapshot=False)
    assert Decimal(report["inputs"]["planned_out_left"]) >= 700
