"""Regression tests for Django bugs found while porting to Java (fixed in both backends)."""
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from tests.helpers import B, create_account, create_category

pytestmark = pytest.mark.django_db


def test_unverified_login_code_is_a_plain_string(settings):
    """The clients check `code === 'email_not_verified'`; a list never matched."""
    settings.REQUIRE_EMAIL_VERIFICATION = True
    get_user_model().objects.create_user(username="newbie", email="n@example.com", password="S3cure-pass!")
    r = APIClient().post("/api/v1/auth/login/", {"username": "newbie", "password": "S3cure-pass!"}, format="json")
    assert r.status_code == 400
    assert r.json()["code"] == "email_not_verified"
    assert isinstance(r.json()["detail"], str)


def test_category_threshold_does_not_overwrite_global(api):
    _, cat = create_category(api)
    url = B + "/config/thresholds/"
    assert api.post(url, {"warn_pct": "70", "critical_pct": "90"}, format="json").status_code == 201
    r = api.post(url, {"category_id": cat, "warn_pct": "50", "critical_pct": "60"}, format="json")
    assert r.status_code == 201
    rows = {t["category_id"]: t for t in api.get(url).json()}
    assert rows[None]["warn_pct"] == "70.0"
    assert rows[cat]["warn_pct"] == "50.0"
    # Updating the category threshold again updates that row only.
    assert api.post(url, {"category_id": cat, "warn_pct": "55", "critical_pct": "60"}, format="json").status_code == 200
    rows = {t["category_id"]: t for t in api.get(url).json()}
    assert rows[None]["warn_pct"] == "70.0" and rows[cat]["warn_pct"] == "55.0"


def test_clone_keeps_source_dates_unless_sent(api):
    url = B + "/personal-budgets/"
    r = api.post(url, {"name": "Trip", "start_date": "2026-03-01", "end_date": "2026-03-31"}, format="json")
    assert r.status_code == 201, r.content
    pk = r.json()["id"]
    clone = api.post("%s%s/clone/" % (url, pk), {}, format="json").json()
    assert clone["start_date"] == "2026-03-01" and clone["end_date"] == "2026-03-31"
    clone = api.post("%s%s/clone/" % (url, pk), {"start_date": "2026-04-01"}, format="json").json()
    assert clone["start_date"] == "2026-04-01" and clone["end_date"] == "2026-03-31"


def test_malformed_input_is_400_not_500(api):
    acc = create_account(api)
    r = api.post(B + "/transactions/", {"date": date.today().isoformat(), "direction": "income",
                                       "description": "Salary", "amount": "10", "account_id": acc}, format="json")
    tid = r.json()["id"]
    assert api.patch("%s/transactions/%s/" % (B, tid), {"date": "31/12/2026"}, format="json").status_code == 400
    assert api.patch("%s/transactions/%s/" % (B, tid), {"amount": "ten"}, format="json").status_code == 400
    assert api.get(B + "/dashboard/", {"year": "abc"}).status_code == 400
    assert api.get(B + "/alerts/", {"month": "x"}).status_code == 400
    assert api.post(B + "/personal-budgets/", {"name": "x", "start_date": "nope"}, format="json").status_code == 400
