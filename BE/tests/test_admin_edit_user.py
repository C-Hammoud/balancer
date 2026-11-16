"""Admin -> user page: editing a user's details (PATCH /admin/users/<id>/)."""
import pytest
from django.core import mail

from api.models import AdminAuditLog
from api.user_profile import get_user_profile, is_email_verified

pytestmark = pytest.mark.django_db

A = "/api/v1/admin/users"


@pytest.fixture
def staff(make_user):
    return make_user("helper", is_staff=True)


@pytest.fixture
def superuser(make_user):
    return make_user("boss", is_staff=True, is_superuser=True)


@pytest.fixture
def staff_api(staff, client_for):
    return client_for(staff)


@pytest.fixture
def super_api(superuser, client_for):
    return client_for(superuser)


def _patch(client, user, **data):
    return client.patch(f"{A}/{user.pk}/", data, format="json")


def test_admin_edits_basic_details_and_it_is_audited(staff_api, staff, make_user):
    target = make_user("alice")
    r = _patch(
        staff_api, target,
        username="alice2", first_name="Alice", last_name="Smith",
        timezone="Asia/Riyadh", country="SA", default_currency="SAR",
    )
    assert r.status_code == 200, r.content
    body = r.json()["user"]
    assert (body["username"], body["first_name"], body["last_name"]) == ("alice2", "Alice", "Smith")
    assert (body["timezone"], body["country"], body["default_currency"]) == ("Asia/Riyadh", "SA", "SAR")
    target.refresh_from_db()
    assert target.username == "alice2"

    row = AdminAuditLog.objects.get(action="edit_user")
    assert row.actor == staff and row.target_user == target
    assert row.detail["changes"]["username"] == {"from": "alice", "to": "alice2"}
    assert set(row.detail["changes"]) == {"username", "first_name", "last_name", "timezone", "country", "default_currency"}


def test_email_change_keeps_verification_and_tells_both_addresses(staff_api, make_user):
    target = make_user("bob")
    mail.outbox.clear()
    r = _patch(staff_api, target, email="bob.new@example.com")
    assert r.status_code == 200, r.content
    target.refresh_from_db()
    assert target.email == "bob.new@example.com"
    assert is_email_verified(target)
    notices = [m for m in mail.outbox if m.subject == "Your Finance Tracker email address was changed"]
    assert sorted(m.to[0] for m in notices) == ["bob.new@example.com", "bob@example.com"]


def test_username_and_email_must_stay_unique(staff_api, make_user):
    make_user("taken")
    target = make_user("carol")
    r = _patch(staff_api, target, username="TAKEN")
    assert r.status_code == 400 and "username" in r.json()
    r = _patch(staff_api, target, email="Taken@Example.com")
    assert r.status_code == 400 and "email" in r.json()
    r = _patch(staff_api, target, timezone="Mars/Olympus")
    assert r.status_code == 400 and "timezone" in r.json()
    assert not AdminAuditLog.objects.filter(action="edit_user").exists()


def test_admin_cannot_edit_superuser_fields_or_other_admins(staff_api, make_user):
    target = make_user("dave")
    r = _patch(staff_api, target, notify_low_balance=False)
    assert r.status_code == 403
    assert get_user_profile(target).notify_low_balance is True

    other_admin = make_user("otheradmin", is_staff=True)
    r = _patch(staff_api, other_admin, first_name="X")
    assert r.status_code == 403

    r = _patch(staff_api, target, is_superuser=True)
    assert r.status_code == 400  # roles go through their own endpoint
    target.refresh_from_db()
    assert not target.is_superuser


def test_superuser_edits_everything(super_api, make_user):
    target = make_user("erin", is_staff=True)
    r = _patch(
        super_api, target,
        first_name="Erin", phone="+966500000000", email_verified=False, setup_status="complete",
        notify_weekly_summaries=False, notify_low_balance=False, notify_setup_nudges=False,
        notify_plan_updates=False, savings_target_pct=35,
    )
    assert r.status_code == 200, r.content
    u = r.json()["user"]
    assert u["first_name"] == "Erin" and u["phone"] == "+966500000000"
    assert u["email_verified"] is False and u["setup_status"] == "complete"
    assert u["savings_target_pct"] == 35
    assert not any(u[f] for f in ("notify_weekly_summaries", "notify_low_balance", "notify_setup_nudges", "notify_plan_updates"))

    r = _patch(super_api, target, setup_status="pending", email_verified=True, savings_target_pct=95)
    assert r.status_code == 400 and "savings_target_pct" in r.json()
    r = _patch(super_api, target, setup_status="pending", email_verified=True)
    assert r.status_code == 200
    profile = get_user_profile(target)
    assert profile.setup_status == "pending" and profile.setup_completed_at is None
    assert is_email_verified(target)


def test_normal_users_cannot_edit(api, make_user):
    target = make_user("frank")
    assert _patch(api, target, first_name="X").status_code == 403


def test_no_changes_writes_no_audit_row(staff_api, make_user):
    target = make_user("gina")
    r = _patch(staff_api, target, username="gina")
    assert r.status_code == 200
    assert not AdminAuditLog.objects.filter(action="edit_user").exists()
