"""Email verification: the emailed link opens the web app, the first activation sends one confirmation email."""
from urllib.parse import parse_qs, urlparse

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from rest_framework.test import APIClient

from api.user_profile import is_email_verified

pytestmark = pytest.mark.django_db
A = "/api/v1/auth"
FRONTEND = "https://app.example.com"


@pytest.fixture(autouse=True)
def _settings(settings):
    settings.FRONTEND_URL = FRONTEND
    settings.REQUIRE_EMAIL_VERIFICATION = True


def _register(client):
    r = client.post(
        A + "/register/",
        {
            "username": "alice",
            "email": "alice@example.com",
            "first_name": "Alice",
            "password": "Tr1cky-horse-77",
            "password_confirm": "Tr1cky-horse-77",
        },
        format="json",
    )
    assert r.status_code == 201, r.content
    return get_user_model().objects.get(username="alice")


def _link_from_welcome_email():
    welcome = mail.outbox[-1]
    body = welcome.alternatives[0][0] if welcome.alternatives else welcome.body
    start = body.index(FRONTEND + "/verify-email?")
    end = min(i for i in (body.find('"', start), body.find("\n", start), body.find(" ", start)) if i != -1)
    return body[start:end].replace("&amp;", "&")


def _uid_token(link):
    q = parse_qs(urlparse(link).query)
    return q["uid"][0], q["token"][0]


def _activation_emails():
    return [m for m in mail.outbox if m.subject == "Your Finance Tracker account is active"]


def test_link_opens_web_app_and_first_activation_sends_one_email():
    client = APIClient()
    user = _register(client)
    link = _link_from_welcome_email()
    uid, token = _uid_token(link)

    r = client.post(A + "/email-verify/confirm/", {"uid": uid, "token": token}, format="json")
    assert r.status_code == 200
    assert r.json() == {
        "detail": "Your account has been activated. You can sign in now.",
        "email_verified": True,
        "already_verified": False,
    }
    assert is_email_verified(user)
    sent = _activation_emails()
    assert len(sent) == 1
    assert sent[0].to == ["alice@example.com"]
    assert FRONTEND + "/login" in sent[0].body

    # Opening the same link again: still fine, but no second email.
    r = client.post(A + "/email-verify/confirm/", {"uid": uid, "token": token}, format="json")
    assert r.status_code == 200
    assert r.json()["already_verified"] is True
    assert r.json()["detail"] == "Your account is already active. You can sign in."
    assert len(_activation_emails()) == 1


def test_bad_token_is_rejected_with_a_generic_message():
    client = APIClient()
    user = _register(client)
    uid, _ = _uid_token(_link_from_welcome_email())
    r = client.post(A + "/email-verify/confirm/", {"uid": uid, "token": "nope"}, format="json")
    assert r.status_code == 400
    assert r.json()["detail"] == "This link is invalid, expired or already used."
    assert not is_email_verified(user)
    assert _activation_emails() == []


def test_old_api_link_redirects_to_the_web_page_without_verifying():
    client = APIClient()
    user = _register(client)
    uid, token = _uid_token(_link_from_welcome_email())
    r = client.get(A + "/email-verify/confirm/", {"uid": uid, "token": token})
    assert r.status_code == 302
    assert r["Location"].startswith(FRONTEND + "/verify-email?")
    assert _uid_token(r["Location"]) == (uid, token)
    assert not is_email_verified(user)


def _register_again(client, **changes):
    data = {
        "username": "alice",
        "email": "alice@example.com",
        "first_name": "Alice",
        "password": "Tr1cky-horse-77",
        "password_confirm": "Tr1cky-horse-77",
        **changes,
    }
    return client.post(A + "/register/", data, format="json")


def test_registering_again_fixes_the_email_of_an_unverified_account():
    client = APIClient()
    user = _register(client)
    old_uid, old_token = _uid_token(_link_from_welcome_email())

    r = _register_again(client, email="alice.new@example.com", last_name="Smith")
    assert r.status_code == 200, r.content
    assert r.json()["updated"] is True and r.json()["email"] == "alice.new@example.com"
    user.refresh_from_db()
    assert (user.email, user.last_name) == ("alice.new@example.com", "Smith")
    assert get_user_model().objects.filter(username="alice").count() == 1
    assert mail.outbox[-1].to == ["alice.new@example.com"]

    # The link sent to the old address no longer works; the new one does.
    r = client.post(A + "/email-verify/confirm/", {"uid": old_uid, "token": old_token}, format="json")
    assert r.status_code == 400
    uid, token = _uid_token(_link_from_welcome_email())
    r = client.post(A + "/email-verify/confirm/", {"uid": uid, "token": token}, format="json")
    assert r.status_code == 200 and is_email_verified(user)


def test_registering_again_needs_the_password_and_an_unverified_account():
    client = APIClient()
    user = _register(client)
    r = _register_again(client, email="evil@example.com", password="Wr0ng-horse-77", password_confirm="Wr0ng-horse-77")
    assert r.status_code == 400 and "username" in r.json()
    user.refresh_from_db()
    assert user.email == "alice@example.com"

    uid, token = _uid_token(_link_from_welcome_email())
    client.post(A + "/email-verify/confirm/", {"uid": uid, "token": token}, format="json")
    r = _register_again(client, email="alice.new@example.com")
    assert r.status_code == 400 and "username" in r.json()  # verified accounts are never changed this way
    user.refresh_from_db()
    assert user.email == "alice@example.com"


def _sign_in(client):
    return client.post(A + "/login/", {"username": "alice", "password": "Tr1cky-horse-77"}, format="json")


def test_signing_in_before_verifying_does_not_break_the_link():
    # The usual path: register, try to sign in, then open the link from the email.
    client = APIClient()
    user = _register(client)
    uid, token = _uid_token(_link_from_welcome_email())

    for _ in range(2):
        r = _sign_in(client)
        assert r.status_code != 200
        assert r.json()["code"] == "email_not_verified"
    user.refresh_from_db()
    assert user.last_login is None  # a refused sign-in is not a login

    r = client.post(A + "/email-verify/confirm/", {"uid": uid, "token": token}, format="json")
    assert r.status_code == 200, r.content
    assert r.json()["already_verified"] is False
    assert len(_activation_emails()) == 1

    r = _sign_in(client)
    assert r.status_code == 200 and "access" in r.json()
    user.refresh_from_db()
    assert user.last_login is not None


def test_verification_link_survives_last_login_but_not_a_new_password():
    from django.utils import timezone

    from api.tokens import email_verification_token

    client = APIClient()
    user = _register(client)
    token = email_verification_token.make_token(user)
    user.last_login = timezone.now()
    user.save(update_fields=["last_login"])
    assert email_verification_token.check_token(user, token)

    user.set_password("An0ther-horse-77")
    user.save()
    assert not email_verification_token.check_token(user, token)


def test_activation_email_failure_does_not_fail_verification(monkeypatch):
    def boom(user):
        raise ConnectionError("SMTP down")

    monkeypatch.setattr("api.emails.send_account_activated_email", boom)
    client = APIClient()
    user = _register(client)
    uid, token = _uid_token(_link_from_welcome_email())
    r = client.post(A + "/email-verify/confirm/", {"uid": uid, "token": token}, format="json")
    assert r.status_code == 200
    assert r.json()["already_verified"] is False
    assert is_email_verified(user)
