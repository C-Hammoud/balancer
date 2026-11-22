"""
Quick add: POST /transactions/bulk/create/ saves several expenses / incomes in one call, all or
nothing. Merchant defaults to the one named after the description; account and currency default
to the user's default expense account and default currency.
"""
import pytest

from budgeting.store import TransactionFS
from tests.helpers import B, create_account, create_category, create_group

pytestmark = pytest.mark.django_db

URL = B + "/transactions/bulk/create/"


def _subs(api, group_id):
    body = api.get(B + "/config/categories/").json()
    rows = body["categories"] if isinstance(body, dict) else body
    return {c["name"]: c["id"] for c in rows if c["group_id"] == group_id}


def _expense(group_id, **extra):
    return {"date": "2026-11-20", "amount": "12.50", "group_id": group_id, "description": "Coffee", **extra}


def test_creates_several_rows_in_one_call(api, user):
    acc = create_account(api)
    group_id, sub_id = create_category(api, "Food", "Groceries")
    r = api.post(URL, {"transactions": [
        _expense(group_id, category_id=sub_id, description="", currency="SAR", account_id=acc),
        _expense(group_id, description="Starbucks", note="with Sam"),
        {"date": "2026-11-21", "direction": "income", "description": "Salary", "amount": "5000"},
    ]}, format="json")
    assert r.status_code == 201, r.content
    body = r.json()
    assert body["created"] == 3
    rows = sorted(TransactionFS.list_all_for_user(str(user.pk)), key=lambda t: t.description)
    by_desc = {t.description: t for t in rows}
    # A picked merchant with no description: the description is the merchant's name.
    assert by_desc["Groceries"].category_id == sub_id
    assert by_desc["Groceries"].currency == "SAR"
    # Same as description: merchant "Starbucks" created under Food.
    subs = _subs(api, group_id)
    assert by_desc["Starbucks"].category_id == subs["Starbucks"]
    assert by_desc["Starbucks"].note == "with Sam"
    assert [c["name"] for c in body["created_categories"]] == ["Starbucks"]
    salary = by_desc["Salary"]
    assert salary.direction == "income" and salary.category_id in (None, "")
    assert all(t.income_source_id == acc for t in rows)


def test_defaults_account_currency_and_direction(api, user):
    create_account(api, "Bank")
    default_acc = create_account(api, "Wallet")
    api.patch("%s/config/accounts/%s/" % (B, default_acc), {"is_default_for_expenses": True}, format="json")
    api.patch("/api/v1/auth/me/", {"default_currency": "SAR"}, format="json")
    group_id = create_group(api, "Food")
    r = api.post(URL, {"transactions": [_expense(group_id)]}, format="json")
    assert r.status_code == 201, r.content
    t = TransactionFS.list_all_for_user(str(user.pk))[0]
    assert (t.direction, t.currency, t.income_source_id, t.source_account) == ("expense", "SAR", default_acc, "Wallet")


def test_same_description_shares_one_new_merchant(api, user):
    create_account(api)
    group_id = create_group(api, "Food")
    r = api.post(URL, {"transactions": [
        _expense(group_id, description="Bakery"),
        _expense(group_id, description="  bakery "),
    ]}, format="json")
    assert r.status_code == 201, r.content
    assert len(r.json()["created_categories"]) == 1
    ids = {t.category_id for t in TransactionFS.list_all_for_user(str(user.pk))}
    assert ids == {_subs(api, group_id)["Bakery"]}


def test_existing_merchant_with_same_name_is_reused(api):
    create_account(api)
    group_id, sub_id = create_category(api, "Food", "Groceries")
    r = api.post(URL, {"transactions": [_expense(group_id, description="Groceries")]}, format="json")
    assert r.status_code == 201, r.content
    assert r.json()["created_categories"] == []
    assert r.json()["transactions"][0]["category_id"] == sub_id


def test_one_bad_row_saves_nothing(api, user):
    create_account(api)
    group_id = create_group(api, "Food")
    _, other_sub = create_category(api, "Car", "Fuel")
    r = api.post(URL, {"transactions": [
        _expense(group_id),
        _expense(group_id, category_id=other_sub),
        {"date": "2026-11-21", "direction": "income", "amount": "10"},
        _expense("", description="x"),
        _expense(group_id, amount="0"),
    ]}, format="json")
    assert r.status_code == 400
    errors = r.json()["rows"]
    assert set(errors) == {"1", "2", "3", "4"}
    assert "category_id" in errors["1"]
    assert "description" in errors["2"]
    assert "group_id" in errors["3"]
    assert "amount" in errors["4"]
    assert TransactionFS.list_all_for_user(str(user.pk)) == []
    assert "Coffee" not in _subs(api, group_id)


def test_expense_needs_description_or_merchant(api):
    create_account(api)
    group_id = create_group(api, "Food")
    r = api.post(URL, {"transactions": [_expense(group_id, description="")]}, format="json")
    assert r.status_code == 400
    assert "description" in r.json()["rows"]["0"]


def test_needs_an_account(api):
    group_id = create_group(api, "Food")
    r = api.post(URL, {"transactions": [_expense(group_id)]}, format="json")
    assert r.status_code == 400
    assert "account_id" in r.json()["rows"]["0"]


def test_other_users_account_rejected(api, make_user, client_for):
    other = client_for(make_user())
    other_acc = create_account(other, "Theirs")
    create_account(api)
    group_id = create_group(api, "Food")
    r = api.post(URL, {"transactions": [_expense(group_id, account_id=other_acc)]}, format="json")
    assert r.status_code == 400
    assert "account_id" in r.json()["rows"]["0"]


def test_empty_and_too_many_rows(api):
    assert api.post(URL, {"transactions": []}, format="json").status_code == 400
    group_id = create_group(api, "Food")
    r = api.post(URL, {"transactions": [_expense(group_id)] * 51}, format="json")
    assert r.status_code == 400
    assert "transactions" in r.json()
