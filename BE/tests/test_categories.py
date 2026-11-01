"""Per-user categories: shared defaults are read-only; users only see their own plus shared."""
import pytest

from budgeting.store import CategoryFS, GroupFS
from tests.helpers import B, add_expense, create_account, create_category

pytestmark = pytest.mark.django_db


@pytest.fixture
def shared():
    g = GroupFS(name="Home", order=0).save()
    c = CategoryFS(name="Rent", group_id=g.pk).save()
    return g, c


def test_users_cannot_change_shared_defaults(api, shared):
    g, c = shared
    assert api.patch("%s/config/groups/%s/" % (B, g.pk), {"name": "Hacked"}, format="json").status_code == 403
    assert api.delete("%s/config/categories/%s/" % (B, c.pk)).status_code == 403
    assert api.patch("%s/config/categories/%s/" % (B, c.pk), {"name": "X"}, format="json").status_code == 403
    assert GroupFS.get(g.pk).name == "Home"


def test_staff_can_change_shared_defaults(make_user, client_for, shared):
    g, _ = shared
    admin = client_for(make_user(is_staff=True))
    assert admin.patch("%s/config/groups/%s/" % (B, g.pk), {"name": "House"}, format="json").status_code == 200
    assert GroupFS.get(g.pk).name == "House"


def test_categories_are_private_per_user(api, make_user, client_for, shared):
    gid, cid = create_category(api, group_name="Hobbies", name="Guitar")
    other = client_for(make_user())

    names = {x["name"] for x in other.get(B + "/categories/").json()["categories"]}
    assert "Guitar" not in names and "Rent" in names
    assert other.patch("%s/config/categories/%s/" % (B, cid), {"name": "Mine"}, format="json").status_code == 404
    assert other.delete("%s/config/groups/%s/" % (B, gid)).status_code == 404

    # Owner sees ownership flags
    mine = {x["name"]: x for x in api.get(B + "/categories/").json()["categories"]}
    assert mine["Guitar"]["can_edit"] is True and mine["Guitar"]["is_shared"] is False
    assert mine["Rent"]["can_edit"] is False and mine["Rent"]["is_shared"] is True


def test_cannot_use_another_users_category(api, make_user, client_for):
    _, cid = create_category(api, group_name="Hobbies", name="Guitar")
    other = client_for(make_user())
    acc = create_account(other)
    r = other.post(
        B + "/transactions/",
        {"date": "2026-10-01", "description": "x", "amount": "5", "direction": "expense",
         "category_id": cid, "account_id": acc},
        format="json",
    )
    assert r.status_code == 400
    assert other.patch("%s/budgets/2026/10/%s/" % (B, cid), {"forecast": "10"}, format="json").status_code == 404


def test_user_can_add_own_subcategory_under_shared_group(api, shared):
    g, _ = shared
    r = api.post(B + "/config/categories/", {"name": "Utilities", "group_id": g.pk}, format="json")
    assert r.status_code == 201
    assert r.json()["can_edit"] is True
    acc = create_account(api)
    add_expense(api, acc, r.json()["id"], 10)


def test_claim_command_assigns_shared(user, shared):
    from django.core.management import call_command

    call_command("claim_shared_categories", username=user.username)
    g, c = shared
    assert GroupFS.get(g.pk).user_id == str(user.pk)
    assert CategoryFS.get(c.pk).user_id == str(user.pk)
