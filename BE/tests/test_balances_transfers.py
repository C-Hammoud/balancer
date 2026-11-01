"""Server-side account balances: one-row transfers, legacy two-row transfers, pending, currencies."""
from datetime import date

import pytest

from budgeting.store import TransactionFS
from tests.helpers import B, add_expense, create_account, create_category

pytestmark = pytest.mark.django_db


def _post(api, **payload):
    payload.setdefault("date", date.today().isoformat())
    r = api.post(B + "/transactions/", payload, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def _income(api, account, amount, **extra):
    return _post(api, direction="income", description=extra.pop("description", "Salary"),
                 amount=str(amount), account_id=account, **extra)


def _balances(api, currency="USD"):
    r = api.get(B + "/config/accounts/balances/", {"report_currency": currency})
    assert r.status_code == 200, r.content
    return {row["account_id"]: row for row in r.json()["accounts"]}


def test_single_row_transfer_moves_money_once(api):
    bank = create_account(api, "Bank")
    wallet = create_account(api, "Wallet")
    _income(api, bank, 1000)
    t = _post(api, direction="transfer", description="To wallet", amount="300",
              account_id=bank, to_account_id=wallet, category_id="anything")
    assert t["to_account_id"] == wallet
    assert t["category_id"] is None  # moving own money is not spending

    rows = _balances(api)
    assert rows[bank]["total"] == "700.00"
    assert rows[wallet]["total"] == "300.00"


def test_transfer_to_same_or_foreign_account_is_rejected(api, make_user, client_for):
    bank = create_account(api, "Bank")
    other = create_account(client_for(make_user()), "Not mine")
    base = {"date": date.today().isoformat(), "direction": "transfer", "description": "x",
            "amount": "10", "account_id": bank}
    r = api.post(B + "/transactions/", {**base, "to_account_id": bank}, format="json")
    assert r.status_code == 400 and "to_account_id" in r.json()
    r = api.post(B + "/transactions/", {**base, "to_account_id": other}, format="json")
    assert r.status_code == 400 and "to_account_id" in r.json()


def test_legacy_two_row_transfer_still_balances(api):
    bank = create_account(api, "Bank")
    wallet = create_account(api, "Wallet")
    _income(api, bank, 500)
    _post(api, direction="transfer", description="Transfer to Wallet", amount="200", account_id=bank)
    _post(api, direction="transfer", description="Transfer from Bank", amount="200", account_id=wallet)
    rows = _balances(api)
    assert rows[bank]["total"] == "300.00"
    assert rows[wallet]["total"] == "200.00"


def test_pending_expense_counts_pending_income_does_not(api):
    _, cat = create_category(api)
    bank = create_account(api, "Bank")
    _income(api, bank, 100)
    bonus = _income(api, bank, 900, description="Bonus", status="pending")
    assert bonus["status"] == "pending"
    add_expense(api, bank, cat, 30, status="pending")
    assert _balances(api)[bank]["total"] == "70.00"

    # Settling the income makes it count.
    r = api.patch("%s/transactions/%s/" % (B, bonus["id"]), {"status": "settled"}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "settled"
    assert _balances(api)[bank]["total"] == "970.00"


def test_multi_currency_totals(api, settings):
    settings.EXCHANGE_RATES = {"SAR": 0.25}  # USD per 1 SAR
    bank = create_account(api, "Bank")
    _income(api, bank, 100, currency="USD")
    _income(api, bank, 100, currency="SAR")
    row = _balances(api)[bank]
    assert row["balances"] == {"SAR": "100.00", "USD": "100.00"}
    assert row["total"] == "125.00"


def test_no_500_row_cap(api, user):
    bank = create_account(api, "Bank")
    for i in range(520):
        TransactionFS(user_id=str(user.pk), date=date.today(), month=date.today().strftime("%Y-%m"),
                      description="Salary", amount=1, direction="income", income_source_id=bank).save()
    assert _balances(api)[bank]["total"] == "520.00"


def test_patch_to_non_transfer_clears_destination(api):
    bank = create_account(api, "Bank")
    wallet = create_account(api, "Wallet")
    t = _post(api, direction="transfer", description="Move", amount="5", account_id=bank, to_account_id=wallet)
    r = api.patch("%s/transactions/%s/" % (B, t["id"]), {"direction": "income"}, format="json")
    assert r.status_code == 200
    assert r.json()["to_account_id"] == ""


def test_invalid_status_rejected(api):
    bank = create_account(api, "Bank")
    t = _income(api, bank, 5)
    r = api.patch("%s/transactions/%s/" % (B, t["id"]), {"status": "maybe"}, format="json")
    assert r.status_code == 400
