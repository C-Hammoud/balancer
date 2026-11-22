"""Admin overview page: the period sections added by ?days=."""
from datetime import timedelta
from unittest import mock

import pytest
from django.utils import timezone

from api import admin_overview
from api.models import AdminAuditLog, Campaign, EmailLog, SupportMessage, SupportTicket, UserProfile

pytestmark = pytest.mark.django_db

URL = "/api/v1/admin/overview/"


@pytest.fixture
def staff(make_user):
    return make_user("helper", is_staff=True)


@pytest.fixture
def staff_api(staff, client_for):
    return client_for(staff)


def _ago(**kw):
    return timezone.now() - timedelta(**kw)


def test_without_days_only_the_counts(staff_api):
    body = staff_api.get(URL).json()
    assert "users_total" in body and "tickets_pool" in body
    assert "users" not in body and "support" not in body


def test_bad_days_is_400(staff_api):
    for bad in ("14", "abc", ""):
        assert staff_api.get(URL, {"days": bad}).status_code == 400


def test_normal_user_refused(api):
    assert api.get(URL, {"days": 30}).status_code == 403


def test_sections_and_counts_kept(staff_api):
    body = staff_api.get(URL, {"days": 7}).json()
    assert body["days"] == 7 and "users_total" in body and "deactivated" in body
    for name in ("users", "support", "messaging", "email", "activity"):
        assert body[name] is not None, name
    assert len(body["users"]["signups"]["series"]) == 7
    assert len(body["support"]["opened"]["series"]) == 7
    assert body["users"]["signups"]["series"][-1]["date"] == timezone.localdate().isoformat()


def test_signups_funnel_and_active(staff_api, staff, make_user, client_for):
    old = make_user("old")
    type(old).objects.filter(pk=old.pk).update(date_joined=_ago(days=40), last_login=_ago(days=35))
    a = make_user("a")          # verified (make_user), setup complete, has a transaction
    b = make_user("b")          # not verified
    UserProfile.objects.filter(user=a).update(setup_status=UserProfile.SETUP_COMPLETE)
    UserProfile.objects.filter(user=b).update(email_verified=False)
    type(a).objects.filter(pk=a.pk).update(last_login=_ago(hours=2))
    acc = client_for(a).post("/api/v1/budgeting/config/accounts/", {"name": "Bank"}, format="json").json()
    client_for(a).post("/api/v1/budgeting/transactions/", {
        "date": timezone.now().date().isoformat(), "direction": "income", "description": "Salary",
        "amount": "100", "account_id": acc["id"],
    }, format="json")

    users = staff_api.get(URL, {"days": 30}).json()["users"]
    # staff, a and b joined in the last 30 days; "old" joined before (and joined 40 days ago
    # is in the previous 30-day window).
    assert users["signups"]["total"] == 3
    assert users["signups"]["previous"] == 1
    assert sum(d["count"] for d in users["signups"]["series"]) == 3
    assert users["funnel"] == {"signed_up": 3, "verified": 2, "setup_complete": 1, "first_transaction": 1}
    assert users["active"]["day"] == 1 and users["active"]["month"] == 1
    assert users["active"]["never"] == 2 and users["active"]["total"] == 4


def test_funnel_skips_store_for_big_groups(staff_api, make_user):
    make_user("a")
    with mock.patch.object(admin_overview, "FUNNEL_STORE_LIMIT", 1):
        funnel = staff_api.get(URL, {"days": 30}).json()["users"]["funnel"]
    assert funnel["signed_up"] == 2 and funnel["first_transaction"] is None


def test_support_times_and_workload(staff_api, staff, make_user):
    customer = make_user("customer")
    other_admin = make_user("second", is_staff=True)
    t1 = SupportTicket.objects.create(user=customer, subject="A", assigned_to=staff)
    t2 = SupportTicket.objects.create(user=customer, subject="B", assigned_to=staff,
                                      status=SupportTicket.STATUS_WAITING_USER)
    t3 = SupportTicket.objects.create(user=customer, subject="C", status=SupportTicket.STATUS_CLOSED)
    SupportTicket.objects.filter(pk=t1.pk).update(created_at=_ago(hours=10), updated_at=_ago(hours=9))
    SupportTicket.objects.filter(pk=t2.pk).update(created_at=_ago(hours=6))
    SupportTicket.objects.filter(pk=t3.pk).update(
        created_at=_ago(hours=30), resolved_at=_ago(hours=26), closed_at=_ago(hours=1),
    )
    m1 = SupportMessage.objects.create(ticket=t1, author=staff, body="hi", from_staff=True)
    m2 = SupportMessage.objects.create(ticket=t2, author=staff, body="hi", from_staff=True)
    SupportMessage.objects.create(ticket=t2, author=None, body="system", from_staff=True)
    SupportMessage.objects.filter(pk=m1.pk).update(created_at=_ago(hours=8))   # 2 h after t1
    SupportMessage.objects.filter(pk=m2.pk).update(created_at=_ago(hours=2))   # 4 h after t2

    sup = staff_api.get(URL, {"days": 7}).json()["support"]
    assert sup["opened"]["total"] == 3 and sup["closed"]["total"] == 1
    assert sup["first_reply_hours"] == 3.0          # median of 2 h and 4 h
    assert sup["resolve_hours"] == 4.0
    assert sup["oldest_waiting"]["id"] == t1.pk and sup["oldest_waiting"]["hours"] >= 9
    load = {r["admin"]["username"]: (r["open"], r["waiting"]) for r in sup["workload"]}
    assert load == {"helper": (1, 1), "second": (0, 0)}
    assert sup["workload"][0]["admin"]["id"] == staff.pk
    assert other_admin.pk in [r["admin"]["id"] for r in sup["workload"]]


def test_email_and_activity(staff_api, staff, make_user):
    u = make_user("customer")
    EmailLog.objects.create(user=u, to=u.email, subject="Hi", status="sent")
    EmailLog.objects.create(user=u, to=u.email, subject="Oops", status="failed", error="SMTP down")
    old = EmailLog.objects.create(to="x@example.com", subject="Old", status="failed")
    EmailLog.objects.filter(pk=old.pk).update(created_at=_ago(days=10))
    AdminAuditLog.objects.create(actor=staff, action="view_user", target_user=u)
    AdminAuditLog.objects.create(actor=staff, action="deactivate", target_user=u)

    body = staff_api.get(URL, {"days": 7}).json()
    email = body["email"]
    assert email["current"] == {"sent": 1, "failed": 1, "console": 0}
    assert email["previous"] == {"sent": 0, "failed": 1, "console": 0}
    assert [f["subject"] for f in email["recent_failures"]] == ["Oops", "Old"]
    assert email["recent_failures"][0]["user"]["username"] == "customer"
    # Opening a user page is not listed as activity.
    assert [r["action"] for r in body["activity"]] == ["deactivate"]


def test_messaging_recent_next_and_stuck(staff_api, staff):
    Campaign.objects.create(name="Draft", subject="s", body="b", channels=["email"], created_by=staff)
    sent = Campaign.objects.create(name="Sent", subject="s", body="b", channels=["email"],
                                   status=Campaign.SENT, created_by=staff)
    Campaign.objects.create(name="Later", subject="s", body="b", channels=["email"], status=Campaign.SCHEDULED,
                            scheduled_at=timezone.now() + timedelta(days=1), created_by=staff)
    Campaign.objects.create(name="Stuck", subject="s", body="b", channels=["email"], status=Campaign.SENDING,
                            started_at=_ago(hours=2), created_by=staff)

    msg = staff_api.get(URL, {"days": 30}).json()["messaging"]
    assert {c["name"] for c in msg["recent"]} == {"Sent", "Later", "Stuck"}
    assert msg["next_scheduled"]["name"] == "Later"
    assert msg["stuck"] == 1 and msg["drafts"] == 1
    row = next(c for c in msg["recent"] if c["id"] == sent.pk)
    assert row["stats"]["recipients"] == 0 and "by_channel" in row["stats"]


def test_failing_section_does_not_break_the_page(staff_api):
    def boom(w):
        raise RuntimeError("store down")

    with mock.patch.dict(admin_overview.SECTIONS, {"support": boom}):
        resp = staff_api.get(URL, {"days": 30})
    assert resp.status_code == 200
    body = resp.json()
    assert body["support"] is None and body["users"] is not None
