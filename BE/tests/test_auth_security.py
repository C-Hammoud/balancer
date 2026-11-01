"""Auth hardening: separate verification tokens, throttles, logout revocation, lookup privacy."""
import pytest
from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode
from rest_framework.test import APIClient

from api.tokens import email_verification_token

pytestmark = pytest.mark.django_db
A = "/api/v1/auth"


def _uid(user):
    return urlsafe_base64_encode(force_bytes(user.pk))


def test_verification_token_cannot_reset_password(user):
    token = email_verification_token.make_token(user)
    r = APIClient().post(
        A + "/password-reset/confirm/",
        {"uid": _uid(user), "token": token, "password": "N3w-strong-pass!", "password_confirm": "N3w-strong-pass!"},
        format="json",
    )
    assert r.status_code == 400
    user.refresh_from_db()
    assert user.check_password("S3cure-pass!")


def test_reset_token_cannot_verify_email(user):
    from api.email_verification import verify_email_with_token

    token = default_token_generator.make_token(user)
    assert verify_email_with_token(_uid(user), token)["ok"] is False


def test_verification_token_verifies_email(user):
    from api.email_verification import verify_email_with_token

    assert verify_email_with_token(_uid(user), email_verification_token.make_token(user))["ok"] is True


def test_login_is_rate_limited(user, settings):
    client = APIClient()
    codes = [
        client.post(A + "/login/", {"username": user.username, "password": "wrong"}, format="json").status_code
        for _ in range(12)
    ]
    assert 429 in codes
    assert codes.index(429) == 10  # default 10/min


def test_password_reset_is_rate_limited(user):
    client = APIClient()
    codes = [
        client.post(A + "/password-reset/", {"identifier": user.email}, format="json").status_code
        for _ in range(7)
    ]
    assert codes[:5] == [200] * 5
    assert codes[5] == 429


def test_logout_revokes_refresh_token(user):
    client = APIClient()
    tokens = client.post(A + "/login/", {"username": user.username, "password": "S3cure-pass!"}, format="json").json()
    assert client.post(A + "/logout/", {"refresh": tokens["refresh"]}, format="json").status_code == 204
    r = client.post(A + "/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
    assert r.status_code == 401


def test_rotated_refresh_token_is_single_use(user):
    client = APIClient()
    tokens = client.post(A + "/login/", {"username": user.username, "password": "S3cure-pass!"}, format="json").json()
    first = client.post(A + "/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
    assert first.status_code == 200 and first.json().get("refresh")
    assert client.post(A + "/token/refresh/", {"refresh": tokens["refresh"]}, format="json").status_code == 401
    assert client.post(A + "/token/refresh/", {"refresh": first.json()["refresh"]}, format="json").status_code == 200


def test_user_lookup_returns_no_identity(api, make_user):
    target = make_user(first_name="Secret", last_name="Person")
    body = api.get("/api/v1/budgeting/personal-budgets/users/lookup/", {"email": target.email}).json()
    assert body["found"] is True
    assert "user" not in body
    assert "Secret" not in str(body) and target.username not in str(body)


def test_health_has_no_side_effects(make_user, monkeypatch):
    called = []
    monkeypatch.setattr("api.user_profile.process_setup_nudges", lambda *a, **k: called.append(1) or {})
    r = APIClient().get("/healthz/")
    assert r.status_code == 200 and r.json() == {"status": "ok"}
    assert called == []
