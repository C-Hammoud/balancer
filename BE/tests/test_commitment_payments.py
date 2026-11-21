"""
Commitment payments: the category comes from the commitment (or the request), the merchant is
optional (default: one named after the commitment), the account defaults to the default expense
account, and the commitment's currency is saved.
"""
from datetime import date

import pytest

from budgeting.store import TransactionFS
from tests.helpers import B, create_account, create_category, create_group
from tests.test_alerts import _commitment_due_alert

pytestmark = pytest.mark.django_db


def _commitment(api, name="Car loan", currency="SAR", **extra):
    r = api.post(B + "/commitments/", {
        "name": name, "amount": "300", "start_date": "2026-10-05", "term_months": 3,
        "frequency": "monthly", "payment_amount": "100", "currency": currency, **extra,
    }, format="json")
    assert r.status_code == 201, r.content
    return r.json()["id"]


def _detail(api, cid):
    return api.get("%s/commitments/%s/" % (B, cid)).json()


def _subs(api, group_id):
    body = api.get(B + "/config/categories/").json()
    rows = body["categories"] if isinstance(body, dict) else body
    return {c["name"]: c["id"] for c in rows if c["group_id"] == group_id}


def _pay(api, cid, **payload):
    """Record the next installment from the Transactions page (commitment payment)."""
    return api.post(B + "/transactions/", {
        "date": "2026-10-05", "direction": "expense", "description": "x", "amount": "1",
        "currency": "USD", "commitment_id": cid, **payload,
    }, format="json")


def test_commitment_saves_and_returns_its_category(api, make_user, client_for):
    transport = create_group(api, "Transport")
    cid = _commitment(api, category_id=transport)
    d = _detail(api, cid)
    assert d["category_id"] == transport and d["category_name"] == "Transport"
    listed = {c["id"]: c for c in api.get(B + "/commitments/").json()}
    assert listed[cid]["category_name"] == "Transport"

    housing = create_group(api, "Housing")
    assert api.patch("%s/commitments/%s/" % (B, cid), {"category_id": housing}, format="json").status_code == 200
    assert _detail(api, cid)["category_id"] == housing
    # Other fields can change without touching the category.
    api.patch("%s/commitments/%s/" % (B, cid), {"reminder_days_before": 5}, format="json")
    assert _detail(api, cid)["category_id"] == housing

    theirs = create_group(client_for(make_user()), "Private")
    r = api.post(B + "/commitments/", {
        "name": "X", "amount": "1", "start_date": "2026-10-05", "term_months": 1, "frequency": "monthly",
        "payment_amount": "1", "category_id": theirs,
    }, format="json")
    assert r.status_code == 400 and "category_id" in r.json()


def test_payment_uses_commitment_category_default_account_and_currency(api, user):
    transport = create_group(api, "Transport")
    create_account(api, "Card")  # the first account becomes the default for expenses
    create_account(api, "Cash")
    cid = _commitment(api, category_id=transport, currency="SAR")

    r = _pay(api, cid)  # no account, no merchant, other currency sent
    assert r.status_code == 201, r.content
    txn = r.json()
    merchant = _subs(api, transport)["Car loan"]  # named after the commitment, created once
    assert txn["category_id"] == merchant
    assert txn["currency"] == "SAR"
    assert txn["source_account"] == "Card"
    assert txn["include_in_utilization"] is True

    # The next payment reuses the same merchant.
    r = _pay(api, cid)
    assert r.status_code == 201 and r.json()["category_id"] == merchant
    assert list(_subs(api, transport)) == ["Car loan"]


def test_payment_can_pick_another_category_or_a_merchant(api, user):
    transport = create_group(api, "Transport")
    food, groceries = create_category(api, "Food", "Groceries")
    acc = create_account(api, "Bank")
    cid = _commitment(api, category_id=transport)

    r = _pay(api, cid, group_id=food, account_id=acc)
    assert r.status_code == 201, r.content
    assert r.json()["category_id"] == _subs(api, food)["Car loan"]
    assert r.json()["account_id"] == acc

    r = _pay(api, cid, category_id=groceries)
    assert r.status_code == 201 and r.json()["category_id"] == groceries
    # A payment's choice does not replace the category saved on the commitment.
    assert _detail(api, cid)["category_id"] == transport


def test_commitment_without_category_needs_one_and_remembers_it(api, user):
    create_account(api)
    cid = _commitment(api)
    r = _pay(api, cid)
    assert r.status_code == 400 and "group_id" in r.json()
    assert not TransactionFS.list_by_user(str(user.pk), limit=10)

    loans = create_group(api, "Loans")
    r = _pay(api, cid, group_id=loans)
    assert r.status_code == 201, r.content
    assert _detail(api, cid)["category_id"] == loans  # remembered for the next payments


def test_payment_without_any_account_is_still_saved(api, user):
    cid = _commitment(api, category_id=create_group(api))
    r = _pay(api, cid)
    assert r.status_code == 201, r.content
    assert r.json()["source_account"] == ""


def test_mark_paid_uses_commitment_category_and_default_account(api, user):
    loans = create_group(api, "Loans")
    create_account(api, "Main bank")
    cid = _commitment(api, category_id=loans, currency="SAR")
    line = _detail(api, cid)["schedule"][0]
    r = api.post("%s/commitments/%s/schedule/%s/pay/" % (B, cid, line["id"]), {"paid_date": "2026-10-05"},
                 format="json")
    assert r.status_code == 200, r.content
    txn = TransactionFS.get(r.json()["transaction_id"])
    assert txn.category_id == _subs(api, loans)["Car loan"]
    assert txn.currency == "SAR" and txn.source_account == "Main bank"

    # Without a category anywhere the installment stays outstanding.
    cid2 = _commitment(api, name="Phone")
    line2 = _detail(api, cid2)["schedule"][0]
    r = api.post("%s/commitments/%s/schedule/%s/pay/" % (B, cid2, line2["id"]), {}, format="json")
    assert r.status_code == 400 and "group_id" in r.json()
    assert _detail(api, cid2)["payments_completed"] == 0


def test_alert_payment_needs_no_merchant_and_uses_default_account(api, user):
    create_account(api, "Main bank")
    loans = create_group(api, "Loans")
    commitment_id, alert = _commitment_due_alert(api, user)
    api.patch("%s/commitments/%s/" % (B, commitment_id), {"category_id": loans}, format="json")

    r = api.post("%s/alerts/%s/record-commitment/" % (B, alert["id"]),
                 {"payment_date": date.today().isoformat()}, format="json")
    assert r.status_code == 201, r.content
    txn = r.json()["transaction"]
    assert txn["category_id"] == _subs(api, loans)["Car loan"]
    assert txn["source_account"] == "Main bank"
    assert txn["currency"] == "USD"
