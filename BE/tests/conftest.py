import os

# Tests always use the Django ORM store; never Firestore or a real mail server.
os.environ["DATA_STORE"] = "sqlite"
os.environ.pop("EMAIL_HOST", None)

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient


@pytest.fixture(autouse=True)
def _notification_emails_to_outbox(settings):
    """Tests check notification emails in Django's in-memory outbox (never sent anywhere),
    whatever NOTIFICATION_EMAILS_ENABLED says in the local .env."""
    settings.NOTIFICATION_EMAILS_ENABLED = True


@pytest.fixture(autouse=True)
def _no_throttle_state():
    from django.core.cache import cache

    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def make_user(db):
    from api.user_profile import mark_email_verified

    counter = {"n": 0}

    def _make(username=None, **extra):
        counter["n"] += 1
        name = username or "user%d" % counter["n"]
        user = get_user_model().objects.create_user(
            username=name, email=name + "@example.com", password="S3cure-pass!", **extra
        )
        mark_email_verified(user)
        return user

    return _make


@pytest.fixture
def user(make_user):
    return make_user()


@pytest.fixture
def client_for():
    def _client(u):
        c = APIClient()
        c.force_authenticate(u)
        return c

    return _client


@pytest.fixture
def api(user, client_for):
    return client_for(user)
