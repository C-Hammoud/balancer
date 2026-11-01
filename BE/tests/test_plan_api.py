"""Planning API: income streams, buckets, preview, suggest/edit/accept/dismiss, notifications, ownership."""
import pytest

from budgeting.store import NotificationFS
from tests.helpers import B, create_category

pytestmark = pytest.mark.django_db


@pytest.fixture
def ready(api):
    home, _ = create_category(api, group_name="Home", name="Rent")
    fun, _ = create_category(api, group_name="Fun", name="Movies")
    r = api.post(B + "/income-streams/", {"name": "Salary", "amount": "4000", "currency": "USD"}, format="json")
    assert r.status_code == 201, r.content
    return {"home": home, "fun": fun, "stream": r.json()["id"]}


def test_income_stream_crud_and_validation(api, ready):
    r = api.post(B + "/income-streams/", {"name": "Freelance", "amount": "600", "currency": "USD",
                                          "frequency": "biweekly"}, format="json")
    assert r.json()["monthly_amount"] == "1300.00"
    body = api.get(B + "/income-streams/").json()
    assert len(body["streams"]) == 2 and body["monthly_total"] == "5300.00"
    assert api.post(B + "/income-streams/", {"name": "", "amount": "-1"}, format="json").status_code == 400
    assert api.patch("%s/income-streams/%s/" % (B, ready["stream"]), {"amount": "4500"}, format="json").json()["amount"] == "4500"
    assert api.delete("%s/income-streams/%s/" % (B, ready["stream"])).status_code == 204


def test_buckets_default_and_update(api, ready):
    rows = {r["group_name"]: r for r in api.get(B + "/plans/buckets/").json()}
    assert rows["Home"]["bucket"] == "needs" and rows["Home"]["is_default"]
    assert rows["Fun"]["bucket"] == "wants"
    r = api.put(B + "/plans/buckets/", {"buckets": {ready["fun"]: "needs"}}, format="json")
    assert {x["group_name"]: x["bucket"] for x in r.json()}["Fun"] == "needs"
    assert api.put(B + "/plans/buckets/", {"buckets": {ready["fun"]: "luxury"}}, format="json").status_code == 400


def test_preview_returns_both_plan_types(api, ready):
    body = api.post(B + "/plans/preview/", {"year": 2026, "month": 11}, format="json").json()
    assert [p["plan_type"] for p in body["plans"]] == ["rule_50_30_20", "spending_based"]
    assert body["plans"][0]["savings_amount"] == "800.00"


def test_suggest_edit_accept_flow(api, ready):
    r = api.post(B + "/plans/", {"year": 2026, "month": 11, "plan_type": "rule_50_30_20"}, format="json")
    assert r.status_code == 201 and r.json()["status"] == "suggested"
    pid = r.json()["id"]
    r = api.patch("%s/plans/%s/" % (B, pid), {"amounts": {ready["fun"]: "1000"}}, format="json")
    assert r.json()["savings_amount"] == "1000.00"
    r = api.post("%s/plans/%s/accept/" % (B, pid))
    assert r.status_code == 200 and r.json()["status"] == "accepted"
    budgets = api.get(B + "/budgets/", {"year": 2026, "month": 11}).json()["rows"]
    assert {row["category_name"]: row["forecast"] for row in budgets}["Fun"] == "1000.00"
    assert api.get(B + "/savings/2026/11/").json()["target"] == "1000.00"
    # accepted plans can no longer be edited
    assert api.patch("%s/plans/%s/" % (B, pid), {"amounts": {ready["fun"]: "5"}}, format="json").status_code == 400


def test_dismissed_plan_cannot_be_accepted(api, ready):
    pid = api.post(B + "/plans/", {"year": 2026, "month": 11}, format="json").json()["id"]
    assert api.post("%s/plans/%s/dismiss/" % (B, pid)).json()["status"] == "dismissed"
    assert api.post("%s/plans/%s/accept/" % (B, pid)).status_code == 400


def test_other_users_cannot_touch_plans_streams_or_notifications(api, user, ready, make_user, client_for):
    other = client_for(make_user())
    pid = api.post(B + "/plans/", {"year": 2026, "month": 11}, format="json").json()["id"]
    n = NotificationFS(user_id=str(user.pk), kind="plan_suggested", title="t").save()
    assert other.get("%s/plans/%s/" % (B, pid)).status_code == 404
    assert other.post("%s/plans/%s/accept/" % (B, pid)).status_code == 404
    assert other.delete("%s/income-streams/%s/" % (B, ready["stream"])).status_code == 404
    assert other.post("/api/v1/notifications/%s/read/" % n.pk).status_code == 404
    assert other.get(B + "/plans/").json() == []


def test_notifications_read_flow(api, user):
    for i in range(3):
        NotificationFS(user_id=str(user.pk), kind="plan_suggested", title="n%d" % i).save()
    assert api.get("/api/v1/notifications/count/").json()["unread"] == 3
    first = api.get("/api/v1/notifications/").json()[0]["id"]
    api.post("/api/v1/notifications/%s/read/" % first)
    assert api.get("/api/v1/notifications/count/").json()["unread"] == 2
    assert api.post("/api/v1/notifications/read-all/").json()["marked"] == 2
    assert api.get("/api/v1/notifications/", {"unread": "1"}).json() == []


def test_profile_plan_settings(api):
    r = api.patch("/api/v1/auth/me/", {"savings_target_pct": 95, "notify_plan_updates": False}, format="json")
    assert r.status_code == 200
    me = api.get("/api/v1/auth/me/").json()
    assert me["savings_target_pct"] == 90 and me["notify_plan_updates"] is False
