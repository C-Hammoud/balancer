"""Bulk actions on transactions: the months list, deleting whole months, and acting on a selection."""
from datetime import date

import pytest

from budgeting.store import TransactionFS
from tests.helpers import B, add_expense, create_account, create_category, create_group

pytestmark = pytest.mark.django_db


def _income(api, account, amount, d, **extra):
    r = api.post(B + "/transactions/", {
        "date": d.isoformat(), "direction": "income", "description": "Salary",
        "amount": str(amount), "account_id": account, **extra,
    }, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def _months(api):
    r = api.get(B + "/transactions/months/")
    assert r.status_code == 200, r.content
    return {row["month"]: row for row in r.json()}


def _ids(user):
    return {t.pk for t in TransactionFS.list_all_for_user(str(user.pk))}


def test_months_list_counts_and_totals_per_currency(api, make_user, client_for):
    _, cat = create_category(api)
    bank = create_account(api)
    add_expense(api, bank, cat, 30, d=date(2026, 9, 3))
    add_expense(api, bank, cat, 20, d=date(2026, 9, 20), currency="SAR")
    _income(api, bank, 1000, date(2026, 9, 1))
    add_expense(api, bank, cat, 5, d=date(2026, 10, 2))
    # Another user's rows never show up.
    other = client_for(make_user())
    _, other_cat = create_category(other)
    add_expense(other, create_account(other), other_cat, 99, d=date(2026, 8, 1))

    r = api.get(B + "/transactions/months/")
    assert [row["month"] for row in r.json()] == ["2026-10", "2026-09"]  # newest first
    sep = _months(api)["2026-09"]
    assert (sep["count"], sep["income_count"], sep["expense_count"]) == (3, 1, 2)
    assert (sep["first_date"], sep["last_date"]) == ("2026-09-01", "2026-09-20")
    assert sep["totals"] == [
        {"currency": "SAR", "income": "0.00", "expense": "20.00"},
        {"currency": "USD", "income": "1000.00", "expense": "30.00"},
    ]


def test_delete_months_removes_only_those_months(api, user, make_user, client_for):
    _, cat = create_category(api)
    bank = create_account(api)
    add_expense(api, bank, cat, 30, d=date(2026, 8, 3))
    add_expense(api, bank, cat, 20, d=date(2026, 9, 3))
    keep = add_expense(api, bank, cat, 10, d=date(2026, 10, 3))
    other_user = make_user()
    other = client_for(other_user)
    _, other_cat = create_category(other)
    add_expense(other, create_account(other), other_cat, 99, d=date(2026, 8, 1))

    r = api.post(B + "/transactions/months/delete/", {"months": ["2026-08", "2026-09"]}, format="json")
    assert r.status_code == 200, r.content
    assert r.json() == {"deleted": 2, "months": ["2026-08", "2026-09"]}
    assert _ids(user) == {keep["id"]}
    assert len(_ids(other_user)) == 1  # the same month of another user is untouched


@pytest.mark.parametrize("payload", [{}, {"months": []}, {"months": ["2026-13"]}, {"months": ["Sept"]}])
def test_delete_months_validates_input(api, payload):
    r = api.post(B + "/transactions/months/delete/", payload, format="json")
    assert r.status_code == 400 and "months" in r.json()


def test_bulk_delete_selected_and_ignores_foreign_ids(api, user, make_user, client_for):
    _, cat = create_category(api)
    bank = create_account(api)
    a = add_expense(api, bank, cat, 1, d=date(2026, 9, 1))
    b = add_expense(api, bank, cat, 2, d=date(2026, 9, 2))
    c = add_expense(api, bank, cat, 3, d=date(2026, 9, 3))
    other_user = make_user()
    other = client_for(other_user)
    _, other_cat = create_category(other)
    foreign = add_expense(other, create_account(other), other_cat, 9)

    r = api.post(B + "/transactions/bulk/", {"ids": [a["id"], b["id"], foreign["id"]], "action": "delete"},
                 format="json")
    assert r.status_code == 200, r.content
    assert r.json() == {"deleted": 2, "missing": 1}
    assert _ids(user) == {c["id"]}
    assert _ids(other_user) == {foreign["id"]}

    # Only foreign ids: nothing found.
    r = api.post(B + "/transactions/bulk/", {"ids": [foreign["id"]], "action": "delete"}, format="json")
    assert r.status_code == 404


def test_bulk_delete_reopens_paid_installments(api):
    r = api.post(B + "/commitments/", {
        "name": "Car loan", "amount": "300", "start_date": "2026-10-05", "term_months": 3,
        "frequency": "monthly", "payment_amount": "100", "currency": "USD",
        "category_id": create_group(api),
    }, format="json")
    cid = r.json()["id"]
    line_id = api.get("%s/commitments/%s/" % (B, cid)).json()["schedule"][0]["id"]
    txn = api.post("%s/commitments/%s/schedule/%s/pay/" % (B, cid, line_id),
                   {"paid_date": "2026-10-05"}, format="json").json()["transaction_id"]

    r = api.post(B + "/transactions/bulk/", {"ids": [txn], "action": "delete"}, format="json")
    assert r.status_code == 200 and r.json()["deleted"] == 1
    assert api.get("%s/commitments/%s/" % (B, cid)).json()["schedule"][0]["status"] == "outstanding"


def test_bulk_update_status_account_and_merchant(api):
    _, groceries = create_category(api, "Food", "Groceries")
    bank = create_account(api, "Bank")
    card = create_account(api, "Card")
    e1 = add_expense(api, bank, None, 12, description="CARREFOUR 123")
    e2 = add_expense(api, bank, groceries, 8, description="Groceries", note="weekly")
    inc = _income(api, bank, 500, date.today())

    ids = [e1["id"], e2["id"], inc["id"]]
    r = api.post(B + "/transactions/bulk/", {
        "ids": ids, "action": "update",
        "changes": {"status": "pending", "account_id": card, "category_id": groceries},
    }, format="json")
    assert r.status_code == 200, r.content
    assert r.json() == {"updated": 3, "skipped": 0, "missing": 0}

    rows = {i: api.get("%s/transactions/%s/" % (B, i)).json() for i in ids}
    assert all(row["status"] == "pending" for row in rows.values())
    assert all(row["income_source_id"] == card for row in rows.values())
    # The merchant applies to expenses only; the bank text is kept in the note.
    assert rows[e1["id"]]["category_id"] == groceries
    assert rows[e1["id"]]["description"] == "Groceries"
    assert rows[e1["id"]]["note"] == "CARREFOUR 123"
    assert rows[e2["id"]]["note"] == "weekly"
    assert rows[inc["id"]]["category_id"] is None and rows[inc["id"]]["description"] == "Salary"

    # Nothing left to change: every row is skipped.
    r = api.post(B + "/transactions/bulk/", {"ids": ids, "action": "update", "changes": {"status": "pending"}},
                 format="json")
    assert r.json() == {"updated": 0, "skipped": 3, "missing": 0}


def test_bulk_update_rejects_bad_changes(api, make_user, client_for):
    create_category(api)
    bank = create_account(api)
    t = add_expense(api, bank, None, 5)
    other = client_for(make_user())
    foreign_account = create_account(other)

    def post(changes, action="update"):
        return api.post(B + "/transactions/bulk/", {"ids": [t["id"]], "action": action, "changes": changes},
                        format="json")

    assert post({"status": "done"}).status_code == 400
    assert post({"account_id": foreign_account}).status_code == 400
    r = post({"category_id": "99999"})  # not a merchant the user can see
    assert r.status_code == 400 and "category_id" in r.json()
    r = post({"amount": "1"})
    assert r.status_code == 400 and "changes" in r.json()
    assert post({}).status_code == 400
    assert post({"status": "pending"}, action="archive").status_code == 400
    r = api.post(B + "/transactions/bulk/", {"ids": [], "action": "delete"}, format="json")
    assert r.status_code == 400 and "ids" in r.json()


# ---- One call: move a selection under a category, each expense keeping its merchant name ----

CATEGORIZE = B + "/transactions/bulk/categorize/"


def _subs(api, group_id):
    r = api.get(B + "/config/categories/")
    assert r.status_code == 200, r.content
    body = r.json()
    rows = body["categories"] if isinstance(body, dict) else body
    return {c["name"]: c["id"] for c in rows if c["group_id"] == group_id}


def test_categorize_keeps_each_merchant_name_in_one_call(api):
    food, groceries = create_category(api, "Food", "Groceries")
    bank = create_account(api, "Bank")
    card = create_account(api, "Card")
    othaim_1 = add_expense(api, bank, None, 54, description="Othaim")
    othaim_2 = add_expense(api, bank, None, 20, description="  othaim ")
    fruits = add_expense(api, bank, None, 69, description="Fruits")
    grocer = add_expense(api, bank, None, 30, description="groceries")  # matches "Groceries" whatever the case
    inc = _income(api, bank, 500, date.today())

    ids = [othaim_1["id"], othaim_2["id"], fruits["id"], grocer["id"], inc["id"]]
    r = api.post(CATEGORIZE, {"ids": ids, "group_id": food, "changes": {"status": "pending", "account_id": card}},
                 format="json")
    assert r.status_code == 200, r.content
    body = r.json()
    assert (body["updated"], body["skipped"], body["missing"], body["no_description"]) == (5, 0, 0, 0)
    # Each new name is created once, under the chosen category, and returned for the web app.
    assert sorted(c["name"] for c in body["created_categories"]) == ["Fruits", "Othaim"]
    assert all(c["group_id"] == food for c in body["created_categories"])

    subs = _subs(api, food)
    assert set(subs) == {"Groceries", "Othaim", "Fruits"}
    rows = {i: api.get("%s/transactions/%s/" % (B, i)).json() for i in ids}
    assert rows[othaim_1["id"]]["category_id"] == subs["Othaim"]
    assert rows[othaim_2["id"]]["category_id"] == subs["Othaim"]
    assert rows[fruits["id"]]["category_id"] == subs["Fruits"]
    assert rows[grocer["id"]]["category_id"] == groceries
    assert all(row["status"] == "pending" and row["income_source_id"] == card for row in rows.values())
    # Income keeps its own description and gets no merchant.
    assert rows[inc["id"]]["category_id"] is None and rows[inc["id"]]["description"] == "Salary"

    # Running it again changes nothing and creates nothing.
    r = api.post(CATEGORIZE, {"ids": ids, "group_id": food, "changes": {"status": "pending"}}, format="json")
    assert r.json()["updated"] == 0 and r.json()["skipped"] == 5 and r.json()["created_categories"] == []


def test_categorize_moves_assigned_expenses_to_another_category(api):
    food, groceries = create_category(api, "Food", "Groceries")
    market = api.post(B + "/config/groups/", {"name": "Market"}, format="json").json()["id"]
    bank = create_account(api)
    t = add_expense(api, bank, groceries, 12, description="Groceries", note="weekly")

    r = api.post(CATEGORIZE, {"ids": [t["id"]], "group_id": market}, format="json")
    assert r.status_code == 200, r.content
    assert [c["name"] for c in r.json()["created_categories"]] == ["Groceries"]
    row = api.get("%s/transactions/%s/" % (B, t["id"])).json()
    assert row["category_id"] == _subs(api, market)["Groceries"] != groceries
    assert row["description"] == "Groceries" and row["note"] == "weekly"


def test_categorize_skips_expenses_without_a_description(api):
    food, _ = create_category(api)
    bank = create_account(api)
    t = add_expense(api, bank, None, 5, description="Unassigned")
    r = api.post(CATEGORIZE, {"ids": [t["id"]], "group_id": food}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["updated"] == 0 and r.json()["no_description"] == 1 and r.json()["created_categories"] == []


def test_categorize_validates_input(api, make_user, client_for):
    food, _ = create_category(api)
    bank = create_account(api)
    t = add_expense(api, bank, None, 5, description="Shop")
    other = client_for(make_user())
    foreign_group, _ = create_category(other, "Theirs", "Private")
    foreign_txn = add_expense(other, create_account(other), None, 7, description="Theirs")

    def post(**payload):
        return api.post(CATEGORIZE, {"ids": [t["id"]], "group_id": food, **payload}, format="json")

    r = post(group_id="")
    assert r.status_code == 400 and "group_id" in r.json()
    assert post(group_id=foreign_group).status_code == 400  # another user's own category
    r = post(changes={"category_id": "1"})
    assert r.status_code == 400 and "changes" in r.json()
    assert post(changes={"status": "done"}).status_code == 400
    r = post(ids=[])
    assert r.status_code == 400 and "ids" in r.json()
    assert post(ids=[foreign_txn["id"]]).status_code == 404
    # Ids that are not the user's are counted as missing and left alone.
    r = post(ids=[t["id"], foreign_txn["id"]])
    assert r.status_code == 200 and r.json()["missing"] == 1
    assert other.get("%s/transactions/%s/" % (B, foreign_txn["id"])).json()["category_id"] is None
