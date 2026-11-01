"""Planned items: CRUD, validation, occurrence dates (month-end clamping, leap years)."""
from datetime import date
from types import SimpleNamespace

import pytest

from budgeting.planned import occurrences
from tests.helpers import B

pytestmark = pytest.mark.django_db

URL = B + "/planned-items/"


def _item(frequency, start, end=None):
    return SimpleNamespace(frequency=frequency, start_date=start, end_date=end)


def test_monthly_clamps_to_month_end_and_keeps_the_day():
    item = _item("monthly", date(2024, 1, 31))
    assert occurrences(item, date(2024, 1, 1), date(2024, 4, 30)) == [
        date(2024, 1, 31), date(2024, 2, 29), date(2024, 3, 31), date(2024, 4, 30),
    ]


def test_yearly_on_leap_day():
    item = _item("yearly", date(2024, 2, 29))
    assert occurrences(item, date(2025, 1, 1), date(2028, 12, 31)) == [
        date(2025, 2, 28), date(2026, 2, 28), date(2027, 2, 28), date(2028, 2, 29),
    ]


def test_weekly_window_and_end_date():
    item = _item("weekly", date(2026, 1, 1), end=date(2026, 1, 29))
    assert occurrences(item, date(2026, 1, 10), date(2026, 3, 1)) == [
        date(2026, 1, 15), date(2026, 1, 22), date(2026, 1, 29),
    ]


def test_once_and_biweekly():
    assert occurrences(_item("once", date(2026, 5, 5)), date(2026, 5, 1), date(2026, 5, 31)) == [date(2026, 5, 5)]
    assert occurrences(_item("once", date(2026, 5, 5)), date(2026, 6, 1), date(2026, 6, 30)) == []
    assert occurrences(_item("biweekly", date(2026, 5, 1)), date(2026, 5, 1), date(2026, 5, 31)) == [
        date(2026, 5, 1), date(2026, 5, 15), date(2026, 5, 29),
    ]


def test_crud(api):
    r = api.post(URL, {"name": "Rent", "amount": "800", "frequency": "monthly",
                       "start_date": "2026-01-01", "is_essential": True}, format="json")
    assert r.status_code == 201, r.content
    item = r.json()
    assert item["kind"] == "expense" and item["is_essential"] is True and item["monthly_amount"] == "800.00"

    listing = api.get(URL).json()
    assert [i["id"] for i in listing["items"]] == [item["id"]]
    assert listing["monthly_expense"] == "800.00"

    r = api.patch(URL + item["id"] + "/", {"amount": "850", "end_date": "2026-12-31"}, format="json")
    assert r.status_code == 200 and r.json()["amount"] == "850.00" and r.json()["end_date"] == "2026-12-31"

    assert api.delete(URL + item["id"] + "/").status_code == 204
    assert api.get(URL).json()["items"] == []


@pytest.mark.parametrize("payload, field", [
    ({"amount": "10", "start_date": "2026-01-01"}, "name"),
    ({"name": "x", "amount": "0", "start_date": "2026-01-01"}, "amount"),
    ({"name": "x", "amount": "abc", "start_date": "2026-01-01"}, "amount"),
    ({"name": "x", "amount": "10", "start_date": "nope"}, "start_date"),
    ({"name": "x", "amount": "10"}, "start_date"),
    ({"name": "x", "amount": "10", "start_date": "2026-01-01", "frequency": "daily"}, "frequency"),
    ({"name": "x", "amount": "10", "start_date": "2026-01-01", "kind": "gift"}, "kind"),
    ({"name": "x", "amount": "10", "start_date": "2026-05-01", "end_date": "2026-01-01"}, "end_date"),
])
def test_validation(api, payload, field):
    r = api.post(URL, payload, format="json")
    assert r.status_code == 400
    assert field in r.json()


def test_other_users_items_are_hidden(api, make_user, client_for):
    other = client_for(make_user())
    item = other.post(URL, {"name": "Gym", "amount": "30", "start_date": "2026-01-01"}, format="json").json()
    assert api.get(URL + item["id"] + "/").status_code == 404
    assert api.patch(URL + item["id"] + "/", {"amount": "1"}, format="json").status_code == 404
    assert api.delete(URL + item["id"] + "/").status_code == 404
