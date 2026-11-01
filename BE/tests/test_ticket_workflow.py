"""Ticket workflow: assignment modes, assignee-only actions, resolve -> confirm -> close, reminders, settings."""
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from api import support
from api.models import AdminAuditLog, SupportSettings, SupportTicket
from budgeting.store import NotificationFS

pytestmark = pytest.mark.django_db

S = "/api/v1/support/tickets/"
A = "/api/v1/admin/tickets/"
SETTINGS = "/api/v1/admin/support-settings/"


@pytest.fixture
def admins(make_user):
    return [make_user("anna", is_staff=True), make_user("bob", is_staff=True)]


@pytest.fixture
def boss(make_user):
    return make_user("boss", is_staff=True, is_superuser=True)


def _open(api, subject="Help"):
    r = api.post(S, {"subject": subject, "category": "bug", "message": "Broken"}, format="json")
    assert r.status_code == 201, r.content
    return SupportTicket.objects.get(pk=r.json()["id"])


def _mode(mode, **extra):
    SupportSettings.objects.update_or_create(pk=1, defaults={"assignment_mode": mode, **extra})


# ---- Assignment ---------------------------------------------------------------------

def test_least_busy_spreads_tickets(api, admins):
    first = _open(api, "one")
    second = _open(api, "two")
    third = _open(api, "three")
    owners = [t.assigned_to for t in (first, second, third)]
    assert owners[0] != owners[1]  # the second ticket goes to the other (less busy) admin
    assert owners[2] == owners[0]  # tie -> whoever was assigned least recently


def test_least_busy_prefers_admin_with_fewer_open_tickets(api, admins):
    anna, bob = admins
    for _ in range(2):
        t = _open(api)
        support.assign(t, anna)
    assert _open(api).assigned_to == bob


def test_round_robin_takes_turns(api, admins):
    _mode("round_robin")
    owners = [_open(api, str(i)).assigned_to for i in range(4)]
    assert owners[0] != owners[1] and owners[0] == owners[2] and owners[1] == owners[3]


def test_pool_mode_and_claim(api, admins, client_for):
    _mode("pool")
    ticket = _open(api)
    assert ticket.assigned_to is None
    anna_api, bob_api = (client_for(a) for a in admins)
    pool = anna_api.get(A, {"view": "pool"}).json()
    assert [t["id"] for t in pool["results"]] == [ticket.pk]
    assert anna_api.post(f"{A}{ticket.pk}/claim/").status_code == 200
    assert bob_api.post(f"{A}{ticket.pk}/claim/").status_code == 409
    assert anna_api.get(A, {"view": "pool"}).json()["count"] == 0
    assert anna_api.get(A, {"view": "mine"}).json()["count"] == 1


def test_no_admins_stays_in_pool_until_job_assigns(api, make_user):
    ticket = _open(api)
    assert ticket.assigned_to is None
    admin = make_user("late", is_staff=True)
    assert support.process_tickets()["assigned"] == 1
    ticket.refresh_from_db()
    assert ticket.assigned_to == admin


def test_deactivated_admin_tickets_move(api, admins, boss, client_for):
    ticket = _open(api)
    owner = ticket.assigned_to
    r = client_for(boss).post(f"/api/v1/admin/users/{owner.pk}/deactivate/")
    assert r.status_code == 200 and r.json()["tickets_reassigned"] == 1
    ticket.refresh_from_db()
    assert ticket.assigned_to not in (None, owner)


# ---- Permissions -------------------------------------------------------------------

def test_only_assignee_or_superuser_acts(api, admins, boss, client_for):
    ticket = _open(api)
    other = next(a for a in admins if a != ticket.assigned_to)
    other_api = client_for(other)
    assert other_api.get(f"{A}{ticket.pk}/").status_code == 200  # can read
    assert other_api.post(f"{A}{ticket.pk}/reply/", {"body": "hi"}, format="json").status_code == 403
    assert other_api.post(f"{A}{ticket.pk}/resolve/", {"message": "done"}, format="json").status_code == 403
    assert other_api.patch(f"{A}{ticket.pk}/", {"assigned_to": other.pk}, format="json").status_code == 403
    boss_api = client_for(boss)
    r = boss_api.patch(f"{A}{ticket.pk}/", {"assigned_to": other.pk}, format="json")
    assert r.status_code == 200 and r.json()["assigned_to"]["id"] == other.pk


# ---- Resolve -> confirm -> close ------------------------------------------------------

def test_resolve_then_user_confirms_closes_and_emails_both(api, user, admins, client_for, settings):
    settings.NOTIFICATION_EMAILS_ENABLED = False  # ticket emails are account emails: still sent
    ticket = _open(api)
    admin = ticket.assigned_to
    mail.outbox.clear()
    r = client_for(admin).post(f"{A}{ticket.pk}/resolve/", {"message": "Re-import works now."}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "resolved"
    assert [m.to for m in mail.outbox] == [[user.email]]
    assert "fixed" in mail.outbox[0].subject.lower()

    mail.outbox.clear()
    r = api.post(f"{S}{ticket.pk}/confirm/", {"fixed": True}, format="json")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "closed" and body["close_reason"] == "user_confirmed"
    assert sorted(m.to[0] for m in mail.outbox) == sorted([user.email, admin.email])
    assert all(m.subject.startswith("Closed:") for m in mail.outbox)
    assert any(n.kind == "support_closed" for n in NotificationFS.list_by_user(str(admin.pk)))
    assert AdminAuditLog.objects.filter(action="ticket_closed", ticket_id=ticket.pk).exists()


def test_not_fixed_goes_back_to_same_admin(api, admins, client_for):
    ticket = _open(api)
    admin = ticket.assigned_to
    client_for(admin).post(f"{A}{ticket.pk}/resolve/", {"message": "Try now"}, format="json")
    mail.outbox.clear()
    r = api.post(f"{S}{ticket.pk}/confirm/", {"fixed": False, "comment": "Same error"}, format="json")
    assert r.status_code == 200 and r.json()["status"] == "open"
    ticket.refresh_from_db()
    assert ticket.assigned_to == admin
    assert [m.to for m in mail.outbox] == [[admin.email]]
    assert any(n.kind == "support_reopened" for n in NotificationFS.list_by_user(str(admin.pk)))


def test_confirm_only_when_resolved(api, admins):
    ticket = _open(api)
    assert api.post(f"{S}{ticket.pk}/confirm/", {"fixed": True}, format="json").status_code == 400


def test_reminder_then_auto_close(api, user, admins, client_for):
    ticket = _open(api)
    admin = ticket.assigned_to
    client_for(admin).post(f"{A}{ticket.pk}/resolve/", {"message": "Fixed"}, format="json")
    now = timezone.now()

    mail.outbox.clear()
    assert support.process_tickets(now + timedelta(days=3, minutes=1))["reminded"] == 1
    assert support.process_tickets(now + timedelta(days=4))["reminded"] == 0  # once only
    assert len(mail.outbox) == 1 and "reminder" in mail.outbox[0].subject.lower()

    mail.outbox.clear()
    assert support.process_tickets(now + timedelta(days=7, minutes=1))["closed"] == 1
    ticket.refresh_from_db()
    assert ticket.status == "closed" and ticket.close_reason == "auto"
    assert sorted(m.to[0] for m in mail.outbox) == sorted([user.email, admin.email])


def test_auto_close_off(api, admins, client_for):
    _mode("least_busy", reminder_days=0, auto_close_days=0)
    ticket = _open(api)
    client_for(ticket.assigned_to).post(f"{A}{ticket.pk}/resolve/", {"message": "Fixed"}, format="json")
    stats = support.process_tickets(timezone.now() + timedelta(days=30))
    assert stats["closed"] == 0 and stats["reminded"] == 0


# ---- Settings ----------------------------------------------------------------------

def test_settings_defaults_and_superuser_only(admins, boss, client_for):
    staff_api, boss_api = client_for(admins[0]), client_for(boss)
    body = staff_api.get(SETTINGS).json()
    assert body["assignment_mode"] == "least_busy" and body["reminder_days"] == 3 and body["saved"] is False
    assert staff_api.patch(SETTINGS, {"assignment_mode": "pool"}, format="json").status_code == 403
    r = boss_api.patch(SETTINGS, {"assignment_mode": "round_robin", "auto_close_days": 10}, format="json")
    assert r.status_code == 200 and r.json()["assignment_mode"] == "round_robin" and r.json()["saved"] is True
    assert boss_api.patch(SETTINGS, {"assignment_mode": "random"}, format="json").status_code == 400
    assert boss_api.patch(SETTINGS, {"reminder_days": 12}, format="json").status_code == 400  # after auto-close


def test_admin_emails_can_be_turned_off(api, admins):
    _mode("least_busy", email_admins=False)
    mail.outbox.clear()
    _open(api)
    assert mail.outbox == []  # no "assigned to you" email
