"""Risk engine: factor thresholds, unknowns, score/level, settings, alerts and the API."""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.core import mail

from budgeting.alerts import evaluate_risk_alerts, refresh_alerts_for_user
from budgeting.risk import DEFAULTS, compute_factors, score
from budgeting.store import BudgetAlertFS
from tests.helpers import B, add_expense, create_account, create_category, set_budget

pytestmark = pytest.mark.django_db

D = Decimal
RISK = "/api/v1/risk/"


def _by_key(factors):
    return {f["key"]: f for f in factors}


def _inputs(**over):
    base = {
        "monthly_income": D("1000"),
        "installments_month": D("0"),
        "liquid": D("5000"),
        "card_debt": D("0"),
        "standing": None,
        "avg_spending": D("1000"),
        "overdue_items": [],
        "balloon_items": [],
        "inflows_left": D("0"),
        "installments_left": D("0"),
        "planned_out_left": D("0"),
        "discretionary_left": D("0"),
    }
    base.update(over)
    return base


# ---- Pure factors ---------------------------------------------------------------

@pytest.mark.parametrize("installments, status", [("300", "ok"), ("360", "warn"), ("499", "warn"), ("500", "high")])
def test_debt_to_income_thresholds(installments, status):
    f = _by_key(compute_factors(_inputs(installments_month=D(installments)), {}))["debt_to_income"]
    assert f["status"] == status


def test_debt_to_income_unknown_without_income():
    f = _by_key(compute_factors(_inputs(monthly_income=None, installments_month=D("100")), {}))["debt_to_income"]
    assert f["status"] == "unknown" and f["explanation"]


def test_overdue_is_high():
    items = [{"name": "Car", "amount": D("100"), "due_date": "2026-01-01"}]
    f = _by_key(compute_factors(_inputs(overdue_items=items), {}))["overdue_installments"]
    assert f["status"] == "high" and f["value"] == 1


@pytest.mark.parametrize("liquid, status", [("5000", "ok"), ("1000", "warn"), ("400", "high"), ("-1", "high")])
def test_balloon_exposure(liquid, status):
    items = [{"name": "Car", "amount": D("500"), "due_date": "2026-06-01"}]
    f = _by_key(compute_factors(_inputs(balloon_items=items, liquid=D(liquid)), {}))["balloon_exposure"]
    assert f["status"] == status


def test_debt_to_assets_uses_standing_and_card_debt():
    standing = {"assets": D("1000"), "liabilities": D("400"), "as_of": None}
    f = _by_key(compute_factors(_inputs(standing=standing, card_debt=D("150")), {}))["debt_to_assets"]
    assert f["value"] == D("55.0") and f["status"] == "warn"


@pytest.mark.parametrize("liquid, status", [("3000", "ok"), ("2999", "warn"), ("999", "high")])
def test_emergency_fund(liquid, status):
    f = _by_key(compute_factors(_inputs(liquid=D(liquid)), {}))["emergency_fund"]
    assert f["status"] == status


def test_liquidity_unknown_without_balance():
    factors = _by_key(compute_factors(_inputs(liquid=None), {}))
    for key in ("emergency_fund", "month_cash_flow"):
        assert factors[key]["status"] == "unknown"


@pytest.mark.parametrize("discretionary, status", [("100", "ok"), ("4950", "warn"), ("6000", "high")])
def test_month_cash_flow(discretionary, status):
    f = _by_key(compute_factors(_inputs(discretionary_left=D(discretionary)), {}))["month_cash_flow"]
    assert f["status"] == status


def test_threshold_overrides_apply():
    f = _by_key(compute_factors(_inputs(installments_month=D("300")), {**DEFAULTS, "dti_warn": D("20")}))
    assert f["debt_to_income"]["status"] == "warn"


def test_score_weights_and_levels():
    def fs(**statuses):
        return [{"key": k, "status": s} for k, s in statuses.items()]

    assert score(fs(debt_to_income="ok", emergency_fund="ok", overdue_installments="ok")) == (100, "low")
    # (20*2 + 100) / 3 = 46.7 -> 47, medium
    assert score(fs(debt_to_income="high", overdue_installments="ok")) == (47, "medium")
    assert score(fs(debt_to_income="high", emergency_fund="high")) == (20, "high")
    assert score(fs(debt_to_income="unknown")) == (None, "unknown")


# ---- API -------------------------------------------------------------------------

def _income(api, account, amount):
    r = api.post(B + "/transactions/", {"date": date.today().isoformat(), "direction": "income",
                                       "description": "Opening balance", "amount": str(amount),
                                       "account_id": account}, format="json")
    assert r.status_code == 201, r.content


def _overdue_commitment(api):
    start = date.today() - timedelta(days=40)
    r = api.post(B + "/commitments/", {"name": "Car loan", "amount": "1200", "start_date": start.isoformat(),
                                       "term_months": 12, "frequency": "monthly", "payment_amount": "100",
                                       "currency": "USD"}, format="json")
    assert r.status_code == 201, r.content
    return r.json()["id"]


def test_report_shape_and_snapshot(api):
    acc = create_account(api)
    _income(api, acc, 5000)
    r = api.get(RISK)
    assert r.status_code == 200, r.content
    body = r.json()
    assert {f["key"] for f in body["factors"]} == {
        "debt_to_income", "overdue_installments", "balloon_exposure",
        "debt_to_assets", "emergency_fund", "month_cash_flow",
    }
    assert body["inputs"]["liquid"] == "5000.00"
    history = api.get(RISK + "history/").json()["points"]
    assert [p["as_of"] for p in history] == [date.today().isoformat()]
    assert history[0]["score"] == body["score"]


def test_risk_alerts_created_emailed_once_and_auto_resolved(api, user):
    acc = create_account(api)
    _income(api, acc, 5000)
    commitment_id = _overdue_commitment(api)
    mail.outbox.clear()
    api.get(RISK, {"refresh": 1})
    risk_alerts = [a for a in api.get(B + "/alerts/").json() if a["alert_type"] == "risk"]
    overdue = [a for a in risk_alerts if a["category_id"] == "risk:overdue_installments"]
    assert len(overdue) == 1 and overdue[0]["severity"] == "CRITICAL"
    sent = len(mail.outbox)
    assert sent >= 1

    evaluate_risk_alerts(user)
    assert len(mail.outbox) == sent  # emailed once

    # Utilization runs never resolve risk alerts.
    refresh_alerts_for_user(user, force=True)
    assert BudgetAlertFS.get(overdue[0]["id"]).is_resolved is False

    # Paying everything clears the condition -> auto resolved.
    for line in api.get("%s/commitments/%s/schedule/" % (B, commitment_id)).json():
        if line["status"] == "outstanding" and line["due_date"] < date.today().isoformat():
            api.post("%s/commitments/%s/schedule/%s/pay/" % (B, commitment_id, line["id"]), {}, format="json")
    evaluate_risk_alerts(user)
    alert = BudgetAlertFS.get(overdue[0]["id"])
    assert alert.is_resolved is True and alert.resolution == "auto"


def test_alerts_disabled_resolves_risk_alerts(api, user):
    acc = create_account(api)
    _income(api, acc, 5000)
    _overdue_commitment(api)
    evaluate_risk_alerts(user)
    assert api.patch(RISK + "settings/", {"alerts_enabled": False}, format="json").status_code == 200
    open_risk = [a for a in api.get(B + "/alerts/").json() if a["alert_type"] == "risk"]
    assert open_risk == []


def test_utilization_alerts_unaffected_by_risk(api, user):
    _, cat = create_category(api)
    acc = create_account(api)
    set_budget(api, cat, 100)
    add_expense(api, acc, cat, 95)
    refresh_alerts_for_user(user, force=True)
    alerts = api.get(B + "/alerts/").json()
    assert {a["alert_type"] for a in alerts} == {"utilization"}  # liquidity unknown: no opening balance


def test_settings_get_patch_validate_and_reset(api, make_user, client_for):
    r = api.get(RISK + "settings/").json()
    assert r["effective"]["dti_warn"] == "36" and r["overrides"]["dti_warn"] is None

    r = api.patch(RISK + "settings/", {"dti_warn": "30", "horizon_months": 3}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["effective"]["dti_warn"] == "30" and r.json()["effective"]["horizon_months"] == "3"

    assert api.patch(RISK + "settings/", {"dti_warn": "60"}, format="json").status_code == 400  # > high (50)
    assert api.patch(RISK + "settings/", {"emergency_warn_months": "0.5"}, format="json").status_code == 400
    assert api.patch(RISK + "settings/", {"horizon_months": 99}, format="json").status_code == 400
    assert api.patch(RISK + "settings/", {"dti_high": "abc"}, format="json").status_code == 400
    foreign = create_account(client_for(make_user()))
    assert api.patch(RISK + "settings/", {"included_account_ids": [foreign]}, format="json").status_code == 400

    r = api.patch(RISK + "settings/", {"dti_warn": None}, format="json")
    assert r.json()["overrides"]["dti_warn"] is None and r.json()["effective"]["dti_warn"] == "36"


def test_settings_and_history_are_per_user(api, make_user, client_for):
    api.patch(RISK + "settings/", {"dti_warn": "20"}, format="json")
    api.get(RISK)
    other = client_for(make_user())
    assert other.get(RISK + "settings/").json()["overrides"]["dti_warn"] is None
    assert other.get(RISK + "history/").json()["points"] == []


# ---- Income and balances feed the risk right away ---------------------------------

def _account(api, name, account_type="bank"):
    r = api.post(B + "/config/accounts/", {"name": name, "account_type": account_type}, format="json")
    assert r.status_code == 201, r.content
    return r.json()["id"]


def test_income_recorded_this_month_counts_as_monthly_income(api):
    acc = _account(api, "Bank")
    assert api.get(RISK).json()["inputs"]["monthly_income"] is None
    _income(api, acc, 3000)
    body = api.get(RISK).json()
    assert body["inputs"]["monthly_income"] == "3000.00"
    assert body["inputs"]["liquid"] == "3000.00"


def test_new_income_changes_the_report(api):
    _, cat = create_category(api)
    acc = _account(api, "Bank")
    _income(api, acc, 100)
    add_expense(api, acc, cat, 90)
    before = api.get(RISK).json()
    _income(api, acc, 5000)
    after = api.get(RISK).json()
    assert D(after["inputs"]["liquid"]) == D(before["inputs"]["liquid"]) + 5000
    assert after["factors"] != before["factors"]


def test_card_holding_money_counts_as_cash(api):
    card = _account(api, "Card", "credit_card")
    _income(api, card, 2000)
    assert api.get(RISK).json()["inputs"]["liquid"] == "2000.00"


def test_money_without_an_account_counts_as_cash(api, user):
    from budgeting.store import TransactionFS

    _account(api, "Bank")
    TransactionFS(user_id=str(user.pk), date=date.today(), month=date.today().strftime("%Y-%m"),
                  description="Salary", amount=D("700"), direction="income").save()
    body = api.get(RISK).json()
    assert body["inputs"]["liquid"] == "700.00"
    assert api.get(B + "/config/accounts/balances/").json()["unassigned"] == "700.00"
