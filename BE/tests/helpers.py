"""Small API helpers for building budgeting fixtures through the public endpoints."""
from datetime import date

B = "/api/v1/budgeting"


def create_category(api, group_name="Food", name="Groceries"):
    g = api.post(B + "/config/groups/", {"name": group_name}, format="json")
    assert g.status_code == 201, g.content
    c = api.post(B + "/config/categories/", {"name": name, "group_id": g.json()["id"]}, format="json")
    assert c.status_code == 201, c.content
    return g.json()["id"], c.json()["id"]


def create_account(api, name="Main bank"):
    r = api.post(B + "/config/accounts/", {"name": name}, format="json")
    assert r.status_code == 201, r.content
    return r.json()["id"]


def set_budget(api, category_id, amount, d=None):
    d = d or date.today()
    r = api.patch(
        "%s/budgets/%d/%d/%s/" % (B, d.year, d.month, category_id), {"forecast": str(amount)}, format="json"
    )
    assert r.status_code == 200, r.content


def add_expense(api, account_id, category_id, amount, d=None, **extra):
    payload = {
        "date": (d or date.today()).isoformat(),
        "description": extra.pop("description", "Shop"),
        "amount": str(amount),
        "direction": "expense",
        "category_id": category_id,
        "account_id": account_id,
        **extra,
    }
    r = api.post(B + "/transactions/", payload, format="json")
    assert r.status_code == 201, r.content
    return r.json()
