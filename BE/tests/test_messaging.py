"""
Admin notification center: templates and placeholders, messages to one user (in-app / email /
SMS stub), account notices on (de)activation, campaigns (audience, test, confirm, batches,
cancel, stats), read / click tracking and marketing unsubscribe.
"""
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from api.messaging.campaigns import process_campaigns
from api.messaging.templates import build_context, render_text
from api.messaging.tokens import click_token, unsubscribe_token
from api.models import AdminAuditLog, Campaign, EmailLog, MessageDelivery, UserProfile
from budgeting.store import NotificationFS
from tests.helpers import create_account

pytestmark = pytest.mark.django_db

A = "/api/v1/admin"


@pytest.fixture
def staff(make_user):
    return make_user("support", is_staff=True)


@pytest.fixture
def boss(make_user):
    return make_user("boss", is_staff=True, is_superuser=True)


@pytest.fixture
def admin_api(staff, client_for):
    return client_for(staff)


def _customer(make_user, name="sam", **extra):
    u = make_user(name, first_name="Sam", **extra)
    return u


def _notifications(user):
    return NotificationFS.list_by_user(str(user.pk), limit=50)


# ---- Rendering ----------------------------------------------------------------------


def test_placeholders_render_and_unknown_ones_stay(make_user):
    u = _customer(make_user)
    ctx = build_context(u, reason="", missing=[{"text": "Add an account"}])
    text = render_text("Hi {first_name} ({username}).\n{reason}\n\n\nTodo:\n{missing_items} {nope}", ctx)
    assert text == "Hi Sam (sam).\n\nTodo:\n• Add an account {nope}"


def test_meta_lists_builtin_templates_and_channels(admin_api):
    r = admin_api.get(A + "/messaging/")
    assert r.status_code == 200
    body = r.json()
    keys = {t["key"] for t in body["templates"]}
    assert {"account_deactivated", "account_reactivated", "missing_data", "custom", "announcement"} <= keys
    assert {c["code"]: c["enabled"] for c in body["channels"]} == {"in_app": True, "email": True, "sms": False}


def test_non_staff_refused(api):
    assert api.get(A + "/messaging/").status_code == 403
    assert api.get(A + "/campaigns/").status_code == 403


# ---- One user -----------------------------------------------------------------------


def test_send_to_user_in_app_and_email(admin_api, make_user, staff):
    u = _customer(make_user)
    r = admin_api.post(f"{A}/users/{u.pk}/messages/", {
        "template_key": "custom", "subject": "Hello {first_name}", "body": "Your report is ready.",
        "link": "/dashboard", "channels": ["in_app", "email", "sms"],
    }, format="json")
    assert r.status_code == 201, r.content
    by_channel = {d["channel"]: d for d in r.json()["deliveries"]}
    assert by_channel["in_app"]["status"] == "sent"
    assert by_channel["email"]["status"] == "sent"
    assert by_channel["sms"]["status"] == "skipped" and "not set up" in by_channel["sms"]["detail"]
    [n] = _notifications(u)
    assert (n.title, n.kind, n.link) == ("Hello Sam", "admin_message", "/dashboard")
    assert mail.outbox[-1].subject == "Hello Sam"
    assert EmailLog.objects.filter(user=u, subject="Hello Sam", status="sent").exists()
    log = AdminAuditLog.objects.get(action="send_message")
    assert log.actor == staff and log.target_user == u
    # History for the user page.
    hist = admin_api.get(f"{A}/users/{u.pk}/messages/").json()
    assert len(hist["deliveries"]) == 3
    assert hist["deliveries"][0]["sent_by"]["username"] == "support"


def test_preview_sends_nothing(admin_api, make_user):
    u = _customer(make_user)
    r = admin_api.post(f"{A}/users/{u.pk}/messages/", {"template_key": "missing_data", "preview": True},
                       format="json")
    assert r.status_code == 200, r.content
    body = r.json()
    assert "Hi Sam" in body["body"]
    assert "Finish setting up your account" in body["body"]
    assert "Add the bank accounts" in body["body"]
    assert MessageDelivery.objects.count() == 0 and not mail.outbox


def test_missing_items_follow_the_data(admin_api, make_user, client_for):
    u = _customer(make_user)
    before = {m["code"] for m in admin_api.get(f"{A}/users/{u.pk}/messages/").json()["missing"]}
    assert {"setup_incomplete", "no_account", "no_budget", "no_recent_transactions"} <= before
    create_account(client_for(u))
    after = {m["code"] for m in admin_api.get(f"{A}/users/{u.pk}/messages/").json()["missing"]}
    assert "no_account" not in after


def test_message_validation(admin_api, make_user):
    u = _customer(make_user)
    url = f"{A}/users/{u.pk}/messages/"
    r = admin_api.post(url, {"template_key": "custom", "subject": "", "channels": []}, format="json")
    assert r.status_code == 400
    assert {"subject", "channels"} <= set(r.json())
    r = admin_api.post(url, {"template_key": "custom", "subject": "x", "body": "y", "channels": ["sms"]},
                       format="json")
    assert r.status_code == 400 and "channels" in r.json()
    r = admin_api.post(url, {"template_key": "custom", "subject": "x", "body": "y", "channels": ["email"],
                             "link": "https://evil.example"}, format="json")
    assert r.status_code == 400 and "link" in r.json()
    assert admin_api.post(url, {"template_key": "nope"}, format="json").status_code == 400


def test_user_without_email_is_skipped_on_email(admin_api, make_user):
    u = _customer(make_user)
    u.email = ""
    u.save()
    r = admin_api.post(f"{A}/users/{u.pk}/messages/", {"template_key": "complete_setup"}, format="json")
    by_channel = {d["channel"]: d["status"] for d in r.json()["deliveries"]}
    assert by_channel == {"in_app": "sent", "email": "skipped"}


def test_deactivate_notifies_by_email_only(admin_api, make_user):
    u = _customer(make_user)
    r = admin_api.post(f"{A}/users/{u.pk}/deactivate/", {"notify": True, "reason": "Duplicate account"},
                       format="json")
    assert r.status_code == 200, r.content
    assert r.json()["notified"] is True
    assert r.json()["notice"] == {"email": "sent"}
    assert "deactivated" in mail.outbox[-1].subject
    assert "Reason: Duplicate account" in mail.outbox[-1].body
    assert _notifications(u) == []
    # Without notify nothing is sent.
    mail.outbox.clear()
    admin_api.post(f"{A}/users/{u.pk}/reactivate/", {}, format="json")
    assert not mail.outbox


def test_reactivate_notifies_email_and_in_app(admin_api, make_user):
    u = _customer(make_user, is_active=False)
    r = admin_api.post(f"{A}/users/{u.pk}/reactivate/", {"notify": True}, format="json")
    assert r.json()["notice"] == {"email": "sent", "in_app": "sent"}
    assert len(_notifications(u)) == 1


def test_reminders_not_sent_to_deactivated_users(admin_api, make_user):
    u = _customer(make_user, is_active=False)
    r = admin_api.post(f"{A}/users/{u.pk}/messages/", {"template_key": "complete_setup"}, format="json")
    assert {d["status"] for d in r.json()["deliveries"]} == {"skipped"}


def test_templates_editable_by_superuser_only(admin_api, boss, client_for):
    url = A + "/message-templates/complete_setup/"
    assert admin_api.patch(url, {"subject": "x"}, format="json").status_code == 403
    boss_api = client_for(boss)
    r = boss_api.patch(url, {"subject": "Almost there, {first_name}"}, format="json")
    assert r.status_code == 200 and r.json()["subject"] == "Almost there, {first_name}"
    created = boss_api.post(A + "/message-templates/", {
        "name": "Ramadan offer", "category": "marketing", "subject": "Hi", "body": "b", "channels": ["email"],
    }, format="json")
    assert created.status_code == 201 and created.json()["key"] == "ramadan-offer"
    assert boss_api.delete(url).status_code == 400  # built-in
    assert boss_api.delete(A + "/message-templates/ramadan-offer/").status_code == 204


# ---- Read / click tracking and unsubscribe ------------------------------------------


def test_in_app_read_is_tracked(admin_api, make_user, client_for):
    u = _customer(make_user)
    admin_api.post(f"{A}/users/{u.pk}/messages/", {"template_key": "complete_setup", "channels": ["in_app"]},
                   format="json")
    [n] = _notifications(u)
    client_for(u).post(f"/api/v1/notifications/{n.pk}/read/")
    assert MessageDelivery.objects.get(channel="in_app").read_at is not None


def test_email_click_is_tracked(admin_api, make_user, client):
    u = _customer(make_user)
    admin_api.post(f"{A}/users/{u.pk}/messages/", {"template_key": "add_transactions", "channels": ["email"]},
                   format="json")
    d = MessageDelivery.objects.get(channel="email")
    assert f"/m/{click_token(d.pk)}" in mail.outbox[-1].body
    r = client.get(f"/api/v1/messages/open/{click_token(d.pk)}/")
    assert r.status_code == 200 and r.json()["link"] == "/budgeting/transactions"
    d.refresh_from_db()
    assert d.clicked_at is not None
    assert client.get("/api/v1/messages/open/forged/").status_code == 404


def test_unsubscribe_link(make_user, client):
    u = _customer(make_user)
    r = client.post("/api/v1/messages/unsubscribe/", {"token": unsubscribe_token(u.pk)},
                    content_type="application/json")
    assert r.status_code == 200
    assert UserProfile.objects.get(user=u).notify_marketing is False
    # Works again (idempotent); a forged token does not.
    assert client.post("/api/v1/messages/unsubscribe/", {"token": unsubscribe_token(u.pk)},
                       content_type="application/json").status_code == 200
    assert client.post("/api/v1/messages/unsubscribe/", {"token": unsubscribe_token(u.pk) + "x"},
                       content_type="application/json").status_code == 400


def test_marketing_preference_in_profile(make_user, client_for):
    u = _customer(make_user)
    api = client_for(u)
    assert api.get("/api/v1/auth/me/").json()["notify_marketing"] is True
    api.patch("/api/v1/auth/me/", {"notify_marketing": False}, format="json")
    assert UserProfile.objects.get(user=u).notify_marketing is False


# ---- Campaigns ----------------------------------------------------------------------


def _campaign(api, **extra):
    payload = {
        "name": "November news", "category": "marketing", "subject": "News for {first_name}",
        "body": "We added quick add.", "link": "/dashboard", "channels": ["in_app", "email"],
        "audience": {"type": "filter"}, **extra,
    }
    r = api.post(A + "/campaigns/", payload, format="json")
    assert r.status_code == 201, r.content
    return r.json()


def _count(api, audience):
    r = api.post(A + "/campaigns/audience/", {"audience": audience}, format="json")
    assert r.status_code == 200, r.content
    return r.json()["count"]


def test_audience_filters(admin_api, make_user, staff):
    old = make_user("old")
    old.date_joined = timezone.now() - timedelta(days=10)
    old.save()
    make_user("new")
    make_user("gone", is_active=False)
    # Active users: support (staff), old, new.
    assert _count(admin_api, {"type": "filter"}) == 3
    assert _count(admin_api, {"type": "filter", "flags": ["setup_stuck"]}) == 1
    assert _count(admin_api, {"type": "filter", "flags": ["no_activity"]}) == 1
    assert _count(admin_api, {"type": "users", "user_ids": [old.pk, staff.pk]}) == 2
    r = admin_api.post(A + "/campaigns/audience/", {"audience": {"type": "filter", "flags": ["bogus"]}},
                       format="json")
    assert r.status_code == 400


def test_campaign_send_flow(admin_api, make_user, staff):
    a = make_user("ann")
    b = make_user("bob")
    UserProfile.objects.filter(user=b).update(notify_marketing=False)
    c = _campaign(admin_api, audience={"type": "users", "user_ids": [a.pk, b.pk]})
    url = f"{A}/campaigns/{c['id']}"

    test = admin_api.post(url + "/test/")
    assert test.status_code == 200
    assert mail.outbox[-1].subject == "[Test] News for support"
    assert MessageDelivery.objects.filter(campaign__isnull=False).count() == 0

    wrong = admin_api.post(url + "/send/", {"confirm_count": 5}, format="json")
    assert wrong.status_code == 409 and wrong.json()["count"] == 2
    r = admin_api.post(url + "/send/", {"confirm_count": 2}, format="json")
    assert r.status_code == 200, r.content
    body = r.json()
    assert body["status"] == "sent"
    stats = body["stats"]
    assert stats["recipients"] == 2 and stats["processed"] == 2 and stats["opted_out"] == 1
    assert stats["by_channel"]["email"]["sent"] == 1 and stats["by_channel"]["email"]["skipped"] == 1
    # Marketing emails carry the unsubscribe link and header.
    msg = [m for m in mail.outbox if m.to == [a.email]][-1]
    assert "/unsubscribe/" in msg.body and "List-Unsubscribe" in msg.extra_headers
    assert [n.kind for n in _notifications(a)] == ["campaign"]
    assert _notifications(b) == []
    assert AdminAuditLog.objects.filter(action="campaign_send").exists()
    # Sent campaigns are locked.
    assert admin_api.patch(url + "/", {"name": "x"}, format="json").status_code == 400
    assert admin_api.post(url + "/send/", {"confirm_count": 2}, format="json").status_code == 400
    deliveries = admin_api.get(url + "/deliveries/?channel=email").json()
    assert deliveries["count"] == 2


def test_campaign_all_users_needs_superuser(admin_api, boss, client_for, make_user):
    make_user("ann")
    c = _campaign(admin_api, audience={"type": "all"})
    assert admin_api.post(f"{A}/campaigns/{c['id']}/send/", {"confirm_count": 3}, format="json").status_code == 403
    r = client_for(boss).post(f"{A}/campaigns/{c['id']}/send/", {"confirm_count": 3}, format="json")
    assert r.status_code == 200, r.content


def test_scheduled_campaign_sent_by_the_job_in_batches(admin_api, make_user):
    users = [make_user(f"u{i}") for i in range(5)]
    c = _campaign(admin_api, channels=["in_app"], audience={"type": "users", "user_ids": [u.pk for u in users]})
    later = (timezone.now() + timedelta(hours=2)).isoformat()
    r = admin_api.post(f"{A}/campaigns/{c['id']}/send/", {"confirm_count": 5, "scheduled_at": later},
                       format="json")
    assert r.json()["status"] == "scheduled"
    assert process_campaigns()["messages"] == 0  # not due yet
    soon = timezone.now() + timedelta(hours=3)
    assert process_campaigns(soon, max_per_run=2, batch_size=2) == {"started": 1, "messages": 2}
    assert Campaign.objects.get(pk=c["id"]).status == "sending"
    # Resumes where it stopped; nobody gets it twice.
    process_campaigns(soon, max_per_run=10, batch_size=2)
    camp = Campaign.objects.get(pk=c["id"])
    assert camp.status == "sent"
    assert camp.deliveries.count() == 5
    assert all(len(_notifications(u)) == 1 for u in users)


def test_cancel_stops_sending(admin_api, make_user):
    users = [make_user(f"u{i}") for i in range(3)]
    c = _campaign(admin_api, channels=["in_app"], audience={"type": "users", "user_ids": [u.pk for u in users]})
    later = (timezone.now() + timedelta(hours=1)).isoformat()
    admin_api.post(f"{A}/campaigns/{c['id']}/send/", {"confirm_count": 3, "scheduled_at": later}, format="json")
    r = admin_api.post(f"{A}/campaigns/{c['id']}/cancel/")
    assert r.json()["status"] == "cancelled"
    process_campaigns(timezone.now() + timedelta(hours=2))
    assert MessageDelivery.objects.count() == 0
    assert admin_api.delete(f"{A}/campaigns/{c['id']}/").status_code == 204


def test_campaign_needs_complete_content(admin_api, make_user):
    make_user("ann")
    c = _campaign(admin_api, subject="", channels=[])
    r = admin_api.post(f"{A}/campaigns/{c['id']}/send/", {"confirm_count": 2}, format="json")
    assert r.status_code == 400
    assert {"subject", "channels"} <= set(r.json())
