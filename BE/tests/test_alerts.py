"""Alert lifecycle: user resolve sticks, auto resolve reopens, snooze, reopen, bulk, pay from alert."""
from datetime import date, timedelta

import pytest
from django.core import mail

from budgeting.alerts import refresh_alerts_for_user
from tests.helpers import B, add_expense, create_account, create_category, set_budget

pytestmark = pytest.mark.django_db


@pytest.fixture
def over_budget(api, user):
    """Food > Groceries budget 100, spent 95 -> WARN alerts for Groceries and its group Food."""
    _, cat = create_category(api)
    acc = create_account(api)
    set_budget(api, cat, 100)
    txn = add_expense(api, acc, cat, 95)
    refresh_alerts_for_user(user, force=True)
    return {"category": cat, "account": acc, "txn": txn}


def _list(api, show="open"):
    r = api.get(B + "/alerts/", {"show": show})
    assert r.status_code == 200
    return r.json()


def _ids(api, category_id, show="open"):
    return [a["id"] for a in _list(api, show) if a["category_id"] == category_id]


def _alert_id(api, over_budget):
    ids = _ids(api, over_budget["category"])
    assert len(ids) == 1
    return ids[0]


def test_warn_alerts_for_subcategory_and_group(api, over_budget):
    alerts = _list(api)
    cats = sorted(a["category_id"] for a in alerts)
    assert len(alerts) == 2
    assert over_budget["category"] in cats
    assert any(c.startswith("group:") for c in cats)
    assert {a["severity"] for a in alerts} == {"WARN"}
    assert {a["state"] for a in alerts} == {"open"}


def test_user_resolve_survives_reevaluation(api, user, over_budget):
    alert_id = _alert_id(api, over_budget)
    assert api.post("%s/alerts/%s/resolve/" % (B, alert_id)).status_code == 200

    refresh_alerts_for_user(user, force=True)  # condition still holds (95%)

    assert _ids(api, over_budget["category"]) == []
    resolved = [a for a in _list(api, "resolved") if a["id"] == alert_id]
    assert resolved and resolved[0]["resolution"] == "user"


def test_auto_resolved_alert_reopens_when_condition_returns(api, user, over_budget):
    alert_id = _alert_id(api, over_budget)
    # Raise the budget so 95 is under 80% -> auto resolve
    set_budget(api, over_budget["category"], 1000)
    refresh_alerts_for_user(user, force=True)
    resolved = [a for a in _list(api, "resolved") if a["id"] == alert_id]
    assert resolved and resolved[0]["resolution"] == "auto"

    set_budget(api, over_budget["category"], 100)
    refresh_alerts_for_user(user, force=True)
    assert _ids(api, over_budget["category"]) == [alert_id]


def test_snooze_hides_from_open_and_badge(api, over_budget):
    before = api.get(B + "/alerts/count/").json()
    alert_id = _alert_id(api, over_budget)
    r = api.post("%s/alerts/%s/snooze/" % (B, alert_id), {"days": 3}, format="json")
    assert r.status_code == 200
    assert r.json()["state"] == "snoozed"
    assert r.json()["snoozed_until"]

    assert _ids(api, over_budget["category"]) == []
    assert _ids(api, over_budget["category"], "snoozed") == [alert_id]
    counts = api.get(B + "/alerts/count/").json()
    assert counts["count"] == before["count"] - 1
    assert counts["snoozed"] == 1

    r = api.delete("%s/alerts/%s/snooze/" % (B, alert_id))
    assert r.status_code == 200
    assert _ids(api, over_budget["category"]) == [alert_id]


def test_snooze_rejects_unknown_duration(api, over_budget):
    alert_id = _alert_id(api, over_budget)
    r = api.post("%s/alerts/%s/snooze/" % (B, alert_id), {"days": 30}, format="json")
    assert r.status_code == 400


def test_expired_snooze_returns_to_open(api, over_budget):
    from django.utils import timezone

    from budgeting.store import BudgetAlertFS

    alert_id = _alert_id(api, over_budget)
    a = BudgetAlertFS.get(alert_id)
    a.snoozed_until = timezone.now() - timedelta(minutes=1)
    a.save()
    assert _ids(api, over_budget["category"]) == [alert_id]


def test_snoozed_alert_is_not_emailed(api, user, over_budget):
    from budgeting.alerts import send_pending_alert_emails
    from budgeting.store import BudgetAlertFS

    for a in _list(api):
        obj = BudgetAlertFS.get(a["id"])
        obj.email_sent = False
        obj.save()
        api.post("%s/alerts/%s/snooze/" % (B, a["id"]), {"days": 1}, format="json")
    mail.outbox.clear()
    assert send_pending_alert_emails(user) == 0
    refresh_alerts_for_user(user, force=True)
    assert mail.outbox == []


def test_reopen(api, over_budget):
    alert_id = _alert_id(api, over_budget)
    api.post("%s/alerts/%s/resolve/" % (B, alert_id))
    r = api.post("%s/alerts/%s/reopen/" % (B, alert_id))
    assert r.status_code == 200
    assert r.json()["state"] == "open"
    assert _ids(api, over_budget["category"]) == [alert_id]


def test_bulk_actions_only_touch_own_alerts(api, user, make_user, client_for, over_budget):
    other = make_user()
    other_api = client_for(other)
    _, cat = create_category(other_api, group_name="Home", name="Rent")
    acc = create_account(other_api)
    set_budget(other_api, cat, 10)
    add_expense(other_api, acc, cat, 50)
    refresh_alerts_for_user(other, force=True)
    other_alert_ids = [a["id"] for a in _list(other_api)]
    assert other_alert_ids

    mine = [a["id"] for a in _list(api)]
    r = api.post(B + "/alerts/bulk/", {"action": "resolve", "ids": mine + other_alert_ids}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["updated"]) == sorted(mine)
    assert sorted(body["failed"]) == sorted(other_alert_ids)
    # The other user alerts are untouched
    assert sorted(a["id"] for a in _list(other_api)) == sorted(other_alert_ids)


def test_bulk_validation(api):
    assert api.post(B + "/alerts/bulk/", {"action": "resolve", "ids": []}, format="json").status_code == 400
    assert api.post(B + "/alerts/bulk/", {"action": "explode", "ids": ["1"]}, format="json").status_code == 400
    r = api.post(B + "/alerts/bulk/", {"action": "snooze", "ids": ["1"], "days": 2}, format="json")
    assert r.status_code == 400


def _commitment_due_alert(api, user):
    due = date.today() + timedelta(days=1)
    r = api.post(
        B + "/commitments/",
        {
            "name": "Car loan",
            "amount": "1200",
            "start_date": due.isoformat(),
            "term_months": 12,
            "frequency": "monthly",
            "payment_amount": "100",
            "currency": "USD",
            "reminder_days_before": 3,
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    refresh_alerts_for_user(user, force=True)
    due_alerts = [a for a in _list(api) if a["alert_type"] == "commitment_due"]
    assert len(due_alerts) == 1
    return r.json()["id"], due_alerts[0]


def test_pay_from_alert_records_transaction_with_account(api, user):
    _, cat = create_category(api, group_name="Loans", name="Car")
    acc = create_account(api)
    commitment_id, alert = _commitment_due_alert(api, user)

    r = api.post(
        "%s/alerts/%s/record-commitment/" % (B, alert["id"]),
        {"category_id": cat, "account_id": acc, "payment_date": date.today().isoformat()},
        format="json",
    )
    assert r.status_code == 201, r.content
    txn = r.json()["transaction"]
    assert txn["account_id"] == acc
    assert txn["amount"] == "100.00"
    assert txn["commitment_id"] == commitment_id

    detail = api.get("%s/commitments/%s/" % (B, commitment_id)).json()
    assert detail["payments_completed"] == 1
    assert all(a["id"] != alert["id"] for a in _list(api))


def test_pay_from_alert_rejects_other_users_account(api, user, make_user, client_for):
    _, cat = create_category(api, group_name="Loans", name="Car")
    other_acc = create_account(client_for(make_user()), name="Not mine")
    _, alert = _commitment_due_alert(api, user)
    r = api.post(
        "%s/alerts/%s/record-commitment/" % (B, alert["id"]),
        {"category_id": cat, "account_id": other_acc},
        format="json",
    )
    assert r.status_code == 400
