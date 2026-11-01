"""Plan triggers: monthly suggestion, income drift, commitment change, overspending, dedupe, opt-out."""
from datetime import date
from decimal import Decimal

import pytest
from django.core import mail
from django.core.management import call_command

from api.user_profile import get_user_profile
from budgeting import plan_triggers, planning
from budgeting.store import BudgetPlanFS, IncomeStreamFS, NotificationFS
from tests.helpers import B, add_expense, create_account, create_category

pytestmark = pytest.mark.django_db
NOV = date(2026, 11, 3)


@pytest.fixture
def income(user):
    return IncomeStreamFS(user_id=str(user.pk), name="Salary", amount=Decimal("4000"), currency="USD").save()


@pytest.fixture
def cats(api):
    _, rent = create_category(api, group_name="Home", name="Rent")
    _, movies = create_category(api, group_name="Fun", name="Movies")
    return {"rent": rent, "movies": movies, "acc": create_account(api)}


def notes(user, kind=None):
    rows = NotificationFS.list_by_user(str(user.pk))
    return [n for n in rows if kind is None or n.kind == kind]


def test_monthly_suggestion_notifies_once(user, income, cats):
    mail.outbox.clear()
    assert plan_triggers.check_monthly(user, NOV) is True
    assert plan_triggers.check_monthly(user, NOV) is False  # pending suggestion exists
    plans = BudgetPlanFS.list_for_month(str(user.pk), 2026, 11)
    assert len(plans) == 1 and plans[0].reason == "monthly"
    n = notes(user, "plan_suggested")
    assert len(n) == 1 and n[0].link == "/budgeting/plan?id=%s" % plans[0].pk
    assert len(mail.outbox) == 1 and "budget plan" in mail.outbox[0].subject.lower()


def test_dismissed_month_is_not_renotified(user, income, cats):
    plan_triggers.check_monthly(user, NOV)
    p = BudgetPlanFS.list_for_month(str(user.pk), 2026, 11)[0]
    p.status = "dismissed"
    p.save()
    assert plan_triggers.check_monthly(user, NOV) is False  # same fingerprint
    assert len(notes(user)) == 1


def test_opt_out_sends_nothing(user, income, cats):
    profile = get_user_profile(user)
    profile.notify_plan_updates = False
    profile.save()
    mail.outbox.clear()
    assert plan_triggers.check_monthly(user, NOV) is False
    assert notes(user) == [] and mail.outbox == []


def test_missing_income_asks_for_income(user, cats):
    assert plan_triggers.check_monthly(user, NOV) is True
    assert [n.kind for n in notes(user)] == ["plan_needs_income"]
    assert BudgetPlanFS.list_for_month(str(user.pk), 2026, 11) == []


def test_income_drift_over_10_percent(api, user, income, cats):
    api.post(B + "/transactions/", {"date": "2026-10-25", "description": "Salary", "amount": "5000",
                                     "direction": "income", "account_id": cats["acc"]}, format="json")
    assert plan_triggers.check_income_change(user, NOV) is True
    n = notes(user, "plan_suggested")[0]
    assert "5,000" in n.body and "more than" in n.body


def test_income_within_10_percent_is_quiet(api, user, income, cats):
    api.post(B + "/transactions/", {"date": "2026-10-25", "description": "Salary", "amount": "4200",
                                     "direction": "income", "account_id": cats["acc"]}, format="json")
    assert plan_triggers.check_income_change(user, NOV) is False


def test_commitment_change_suggests_plan(api, user, income, cats):
    r = api.post(B + "/commitments/", {
        "name": "Car loan", "amount": "12000", "start_date": date.today().isoformat(), "term_months": 12,
        "frequency": "monthly", "payment_amount": "1000", "currency": "USD"}, format="json")
    assert r.status_code == 201
    n = notes(user, "plan_suggested")
    assert len(n) == 1 and "Car loan" in n[0].body
    plan = planning.plan_to_dict(BudgetPlanFS.get(n[0].related_id))
    assert plan["reason"] == "commitment_change" and plan["commitments_total"] == Decimal("1000")


def test_overspending_mid_month(api, user, income, cats):
    obj = planning.save_plan(user, planning.build_plan(user, 2026, 11, "rule_50_30_20", "USD"))
    planning.accept_plan(user, obj)  # plans 800 savings
    add_expense(api, cats["acc"], cats["movies"], 3000, d=date(2026, 11, 10))
    assert plan_triggers.check_overspending(user, date(2026, 11, 10)) is False  # before day 15
    assert plan_triggers.check_overspending(user, date(2026, 11, 16)) is True
    assert plan_triggers.check_overspending(user, date(2026, 11, 17)) is False  # once per month


def test_review_command(user, income, cats, capsys):
    call_command("review_budget_plans", username=user.username)
    assert "Reviewed 1 user(s)" in capsys.readouterr().out
