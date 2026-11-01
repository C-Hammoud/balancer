"""Money logic: loan pay/unpay creates/removes expenses, regenerate keeps history, savings currency."""
from datetime import date
from decimal import Decimal

import pytest

from api.currency import convert_amount
from budgeting.services import savings_actual
from budgeting.store import TransactionFS
from tests.helpers import B, create_account

pytestmark = pytest.mark.django_db


def _loan(api, start, currency="USD", term=3, payment="100"):
    r = api.post(
        B + "/commitments/",
        {"name": "Car loan", "amount": "300", "start_date": start.isoformat(), "term_months": term,
         "frequency": "monthly", "payment_amount": payment, "currency": currency},
        format="json",
    )
    assert r.status_code == 201, r.content
    cid = r.json()["id"]
    return cid, api.get("%s/commitments/%s/" % (B, cid)).json()["schedule"]


def _expenses(user, month):
    return [t for t in TransactionFS.list_by_user(str(user.pk), month=month) if t.direction == "expense"]


def test_marking_paid_records_expense_so_savings_do_not_rise(api, user):
    cid, schedule = _loan(api, date(2026, 10, 5))
    before = savings_actual(user, 2026, 10)
    assert before == Decimal("-100")  # outstanding installment counts against savings

    line = schedule[0]
    r = api.post("%s/commitments/%s/schedule/%s/pay/" % (B, cid, line["id"]),
                 {"paid_date": "2026-10-05"}, format="json")
    assert r.status_code == 200 and r.json()["transaction_id"]
    assert len(_expenses(user, "2026-10")) == 1
    assert savings_actual(user, 2026, 10) == before  # no phantom gain


def test_pay_is_idempotent(api, user):
    cid, schedule = _loan(api, date(2026, 10, 5))
    url = "%s/commitments/%s/schedule/%s/pay/" % (B, cid, schedule[0]["id"])
    api.post(url, {"paid_date": "2026-10-05"}, format="json")
    api.post(url, {"paid_date": "2026-10-05"}, format="json")
    assert len(_expenses(user, "2026-10")) == 1


def test_unpay_removes_the_expense(api, user):
    cid, schedule = _loan(api, date(2026, 10, 5))
    line_id = schedule[0]["id"]
    api.post("%s/commitments/%s/schedule/%s/pay/" % (B, cid, line_id), {"paid_date": "2026-10-05"}, format="json")
    r = api.post("%s/commitments/%s/schedule/%s/unpay/" % (B, cid, line_id))
    assert r.status_code == 200 and r.json()["status"] == "outstanding"
    assert _expenses(user, "2026-10") == []


def test_deleting_payment_transaction_reopens_installment(api, user):
    cid, schedule = _loan(api, date(2026, 10, 5))
    line_id = schedule[0]["id"]
    txn_id = api.post("%s/commitments/%s/schedule/%s/pay/" % (B, cid, line_id),
                      {"paid_date": "2026-10-05"}, format="json").json()["transaction_id"]
    assert api.delete("%s/transactions/%s/" % (B, txn_id)).status_code == 204
    lines = api.get("%s/commitments/%s/" % (B, cid)).json()["schedule"]
    assert lines[0]["status"] == "outstanding"


def test_line_patch_to_paid_records_expense(api, user):
    cid, schedule = _loan(api, date(2026, 10, 5))
    r = api.patch("%s/commitments/%s/schedule/%s/" % (B, cid, schedule[0]["id"]),
                  {"payment_date": "2026-10-07", "status": "paid"}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "paid"
    exp = _expenses(user, "2026-10")
    assert len(exp) == 1 and exp[0].date == date(2026, 10, 7)


def test_regenerate_keeps_paid_history(api, user):
    cid, schedule = _loan(api, date(2026, 10, 5))
    paid_id = schedule[0]["id"]
    api.post("%s/commitments/%s/schedule/%s/pay/" % (B, cid, paid_id), {"paid_date": "2026-10-05"}, format="json")

    r = api.post("%s/commitments/%s/regenerate-schedule/" % (B, cid))
    assert r.status_code == 200
    lines = r.json()["schedule"]
    assert len(lines) == 3
    assert [l["id"] for l in lines if l["status"] == "paid"] == [paid_id]
    txn = _expenses(user, "2026-10")[0]
    assert txn.schedule_line_id == paid_id  # transaction still points at a real line


def test_changing_terms_keeps_paid_lines(api, user):
    cid, schedule = _loan(api, date(2026, 10, 5))
    api.post("%s/commitments/%s/schedule/%s/pay/" % (B, cid, schedule[0]["id"]),
             {"paid_date": "2026-10-05"}, format="json")
    api.patch("%s/commitments/%s/" % (B, cid), {"term_months": 6}, format="json")
    detail = api.get("%s/commitments/%s/" % (B, cid)).json()
    assert detail["payments_total"] == 6
    assert detail["payments_completed"] == 1


def test_savings_convert_currencies(api, user):
    acc = create_account(api)
    api.patch("/api/v1/auth/me/", {"default_currency": "USD"}, format="json")
    api.post(B + "/transactions/", {"date": "2026-10-01", "description": "Salary", "amount": "3750",
                                     "currency": "SAR", "direction": "income", "account_id": acc}, format="json")
    api.post(B + "/transactions/", {"date": "2026-10-02", "description": "Rent", "amount": "500",
                                     "currency": "USD", "direction": "expense", "account_id": acc}, format="json")
    # 3750 SAR = 1000 USD; mixing units would give 3250
    assert savings_actual(user, 2026, 10, report_currency="USD") == Decimal("500.00")
    r = api.get(B + "/savings/2026/10/")
    assert r.status_code in (200, 404)


def test_lbp_rate_is_current():
    # ~89,500 LBP per USD (was hard-coded as 100 LBP per USD)
    assert convert_amount(Decimal("89500"), "LBP", "USD") == Decimal("1.00")
    assert convert_amount(Decimal("3.75"), "SAR", "USD") == Decimal("1.00")
