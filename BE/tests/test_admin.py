"""Admin & customer-support API: roles, users, support actions, audit log, email log."""
from datetime import timedelta

import pytest
from django.core import mail
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import AdminAuditLog, EmailLog, UserProfile

pytestmark = pytest.mark.django_db

A = "/api/v1/admin"
PASSWORD = "S3cure-pass!"


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


def _login(username, password=PASSWORD):
    return APIClient().post("/api/v1/auth/login/", {"username": username, "password": password}, format="json")


# ---- Access ----------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/overview/", "/users/", "/tickets/", "/audit-log/", "/staff/"])
def test_normal_users_get_403(api, path):
    assert api.get(A + path).status_code == 403


def test_me_exposes_roles(api, staff_api):
    assert api.get("/api/v1/auth/me/").json()["is_staff"] is False
    me = staff_api.get("/api/v1/auth/me/").json()
    assert me["is_staff"] is True and me["is_superuser"] is False


def test_set_admin_command(make_user):
    u = make_user("newadmin")
    call_command("set_admin", "newadmin", "--superuser")
    u.refresh_from_db()
    assert u.is_staff and u.is_superuser
    call_command("set_admin", "newadmin@example.com", "--remove")
    u.refresh_from_db()
    assert not u.is_staff and not u.is_superuser


def test_only_superusers_change_roles(staff_api, super_api, make_user):
    target = make_user("target")
    url = f"{A}/users/{target.pk}/role/"
    assert staff_api.post(url, {"is_staff": True}, format="json").status_code == 403
    r = super_api.post(url, {"is_staff": True}, format="json")
    assert r.status_code == 200 and r.json()["user"]["is_staff"] is True
    assert super_api.post(url, {"is_staff": False}, format="json").json()["user"]["is_staff"] is False
    assert AdminAuditLog.objects.filter(action="grant_staff", target_user=target).exists()


def test_cannot_change_own_role_or_deactivate_self(super_api, superuser):
    assert super_api.post(f"{A}/users/{superuser.pk}/role/", {"is_staff": False}, format="json").status_code == 400
    assert super_api.post(f"{A}/users/{superuser.pk}/deactivate/").status_code == 400


def test_last_superuser_cannot_be_deactivated(staff_api, superuser):
    assert staff_api.post(f"{A}/users/{superuser.pk}/deactivate/").status_code == 400


# ---- Users list and flags ------------------------------------------------------------

def test_search_and_flags(staff_api, make_user):
    old = make_user("oldie")
    UserProfile.objects.filter(user=old).update(email_verified=False)
    old.date_joined = timezone.now() - timedelta(days=10)
    old.save()
    make_user("fresh")

    body = staff_api.get(A + "/users/", {"q": "oldi"}).json()
    assert body["count"] == 1
    codes = {f["code"] for f in body["results"][0]["flags"]}
    assert {"email_unverified", "setup_stuck", "no_activity"} <= codes

    flagged = staff_api.get(A + "/users/", {"flag": "email_unverified"}).json()
    assert [r["username"] for r in flagged["results"]] == ["oldie"]
    no_activity = staff_api.get(A + "/users/", {"flag": "no_activity"}).json()
    assert "oldie" in [r["username"] for r in no_activity["results"]]
    assert staff_api.get(A + "/users/", {"flag": "nope"}).status_code == 400


def test_overview_counts(staff_api, make_user):
    u = make_user("x")
    u.is_active = False
    u.save()
    body = staff_api.get(A + "/overview/").json()
    assert body["deactivated"] == 1 and body["users_total"] >= 2


def test_user_detail_is_audited(staff_api, staff, make_user, client_for):
    target = make_user("customer")
    acc = client_for(target).post("/api/v1/budgeting/config/accounts/", {"name": "Bank"}, format="json").json()
    client_for(target).post("/api/v1/budgeting/transactions/", {
        "date": timezone.now().date().isoformat(), "direction": "income", "description": "Salary",
        "amount": "100", "account_id": acc["id"],
    }, format="json")
    body = staff_api.get(f"{A}/users/{target.pk}/").json()
    assert body["user"]["username"] == "customer"
    assert body["transactions_count"] == 1 and len(body["recent_transactions"]) == 1
    assert body["accounts"][0]["total"] == "100.00"
    assert AdminAuditLog.objects.filter(actor=staff, action="view_user", target_user=target).exists()


# ---- Support actions ------------------------------------------------------------------

def test_resend_and_mark_verified(staff_api, make_user):
    target = make_user("unverified")
    UserProfile.objects.filter(user=target).update(email_verified=False)
    mail.outbox.clear()
    r = staff_api.post(f"{A}/users/{target.pk}/resend-verification/")
    assert r.status_code == 200 and r.json()["email_sent"] is True
    assert len(mail.outbox) == 1 and target.email in mail.outbox[0].to

    assert _login("unverified").status_code == 400  # not verified yet
    assert staff_api.post(f"{A}/users/{target.pk}/mark-verified/").status_code == 200
    assert _login("unverified").status_code == 200
    assert staff_api.post(f"{A}/users/{target.pk}/resend-verification/").status_code == 400  # already verified


def test_send_password_reset(staff_api, make_user):
    target = make_user("forgetful")
    mail.outbox.clear()
    r = staff_api.post(f"{A}/users/{target.pk}/send-password-reset/")
    assert r.status_code == 200 and r.json()["email_sent"] is True
    assert "reset" in mail.outbox[0].subject.lower()
    assert AdminAuditLog.objects.filter(action="send_reset", target_user=target).exists()


def test_deactivate_signs_out_and_reactivate_restores(staff_api, make_user):
    target = make_user("blocked")
    tokens = _login("blocked").json()
    r = staff_api.post(f"{A}/users/{target.pk}/deactivate/")
    assert r.status_code == 200 and r.json()["sessions_revoked"] >= 1

    assert _login("blocked").status_code == 401
    refresh = APIClient().post("/api/v1/auth/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
    assert refresh.status_code == 401
    me = APIClient(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}").get("/api/v1/auth/me/")
    assert me.status_code == 401

    assert staff_api.post(f"{A}/users/{target.pk}/reactivate/").status_code == 200
    assert _login("blocked").status_code == 200


def test_last_login_is_recorded(make_user):
    u = make_user("loginner")
    assert u.last_login is None
    assert _login("loginner").status_code == 200
    u.refresh_from_db()
    assert u.last_login is not None


def test_email_log_records_sent_and_failed(make_user, monkeypatch):
    from api.emails import send_verification_email

    u = make_user("logged")
    send_verification_email(u)
    assert EmailLog.objects.filter(user=u, status="sent", kind="account").exists()

    def boom(self, *a, **k):
        raise OSError("SMTP down")

    monkeypatch.setattr("django.core.mail.EmailMultiAlternatives.send", boom)
    assert send_verification_email(u) is False
    failed = EmailLog.objects.get(user=u, status="failed")
    assert "SMTP down" in failed.error
