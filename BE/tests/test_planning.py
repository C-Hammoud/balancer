"""Planning engine: 50/30/20 (+ debt-aware), spending-based, currency, rounding, accept."""
from datetime import date
from decimal import Decimal

import pytest

from budgeting import planning
from budgeting.store import BudgetFS, BudgetPlanFS, IncomeStreamFS, SavingsFS
from tests.helpers import B, add_expense, create_account, create_category

pytestmark = pytest.mark.django_db
Y, M = 2026, 11  # plan month; history = Aug-Oct 2026
D = Decimal


@pytest.fixture
def setup(api, user):
    home_g, rent = create_category(api, group_name="Home", name="Rent")      # needs (keyword)
    fun_g, movies = create_category(api, group_name="Fun", name="Movies")    # wants
    acc = create_account(api)
    IncomeStreamFS(user_id=str(user.pk), name="Salary", amount=D("5000"), currency="USD").save()
    return {"home": home_g, "fun": fun_g, "rent": rent, "movies": movies, "acc": acc}


def loan(api, payment):
    r = api.post(B + "/commitments/", {
        "name": "Loan", "amount": str(payment * 12), "start_date": "2026-11-10", "term_months": 12,
        "frequency": "monthly", "payment_amount": str(payment), "currency": "USD"}, format="json")
    assert r.status_code == 201, r.content


def history(api, s, home, fun):
    for m in (8, 9, 10):
        add_expense(api, s["acc"], s["rent"], home, d=date(2026, m, 5))
        add_expense(api, s["acc"], s["movies"], fun, d=date(2026, m, 6))


def lines(plan):
    return {l["group_name"]: l["amount"] for l in plan["lines"]}


def build(user, kind="rule_50_30_20", pct=20, currency="USD"):
    return planning.build_plan(user, Y, M, kind, currency, savings_pct=pct)


def test_50_30_20_basic(user, setup):
    p = build(user)
    assert lines(p) == {"Home": D("2500"), "Fun": D("1500")}
    assert p["savings_amount"] == D("1000") and p["savings_pct"] == 20
    assert p["warnings"] == []


def test_commitments_come_out_of_needs(api, user, setup):
    loan(api, 1500)
    p = build(user)
    assert p["commitments_total"] == D("1500")
    assert lines(p) == {"Home": D("1000"), "Fun": D("1500")}
    assert p["savings_amount"] == D("1000")


def test_debt_aware_shift(api, user, setup):
    loan(api, 2000)  # 40% of income
    p = build(user)
    assert lines(p) == {"Home": D("1000"), "Fun": D("1250")}
    assert p["savings_amount"] == D("750")
    assert any("60/25/15" in w for w in p["warnings"])


def test_heavy_commitments_keep_essentials_and_5pct_savings(api, user, setup):
    loan(api, 3000)  # 60% of income
    p = build(user)
    assert lines(p)["Home"] == D("750")
    assert p["savings_amount"] == D("250")
    assert len(p["warnings"]) == 2


def test_spending_based_surplus_goes_to_savings(api, user, setup):
    history(api, setup, 1800, 1000)
    p = build(user, "spending_based")
    assert p["history_months"] == 3
    assert lines(p) == {"Home": D("1800"), "Fun": D("1000")}
    assert p["savings_amount"] == D("2200")


def test_spending_based_trims_wants_to_hit_target(api, user, setup):
    history(api, setup, 1800, 1000)
    loan(api, 1500)
    p = build(user, "spending_based")
    assert lines(p) == {"Home": D("1800"), "Fun": D("700")}
    assert p["savings_amount"] == D("1000")


def test_spending_based_warns_when_target_unreachable(api, user, setup):
    history(api, setup, 1800, 1000)
    loan(api, 2500)
    p = build(user, "spending_based")
    assert lines(p)["Fun"] == D("700")
    assert any("less than your 20%" in w for w in p["warnings"])


def test_spending_based_without_history_falls_back(user, setup):
    p = build(user, "spending_based")
    assert p["effective_type"] == "rule_50_30_20"
    assert any("No spending history" in w for w in p["warnings"])


def test_income_converted_to_plan_currency(user, setup):
    for s in IncomeStreamFS.list_by_user(str(user.pk)):
        s.delete()
    IncomeStreamFS(user_id=str(user.pk), name="Salary", amount=D("3750"), currency="SAR").save()
    IncomeStreamFS(user_id=str(user.pk), name="Side", amount=D("1200"), currency="USD", frequency="yearly").save()
    assert build(user)["income_total"] == D("1100")  # 1000 + 100


def test_lbp_amounts_round_to_thousands(user, setup):
    p = build(user, currency="LBP")
    assert all(l["amount"] % 1000 == 0 for l in p["lines"])


def test_no_income_gives_zero_plan(user, setup):
    for s in IncomeStreamFS.list_by_user(str(user.pk)):
        s.delete()
    p = build(user)
    assert all(l["amount"] == 0 for l in p["lines"])
    assert any("Add your expected income" in w for w in p["warnings"])


def test_accept_writes_budgets_and_savings_and_supersedes(user, setup):
    first = planning.save_plan(user, build(user))
    second = planning.save_plan(user, build(user, "spending_based"))
    assert BudgetPlanFS.get(first.pk).status == "superseded"
    planning.accept_plan(user, second)
    uid = str(user.pk)
    assert BudgetFS.get_by_user_group_month(uid, setup["home"], Y, M).forecast == D("2500")
    assert SavingsFS.get_by_user_month(uid, Y, M).target == D("1000")
    assert BudgetPlanFS.get(second.pk).status == "accepted"


def test_editing_lines_recomputes_savings(user, setup):
    obj = planning.save_plan(user, build(user))
    planning.update_plan_lines(obj, {setup["fun"]: "1000"})
    plan = planning.plan_to_dict(BudgetPlanFS.get(obj.pk))
    assert plan["savings_amount"] == D("1500")
    with pytest.raises(ValueError):
        planning.update_plan_lines(obj, {setup["fun"]: "-5"})
