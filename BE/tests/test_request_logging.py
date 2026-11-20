"""Every API call writes one log line with method, path, status, duration, user and a request id."""
import logging

import pytest
from rest_framework.test import APIClient

from api.request_logging import RequestIdFilter
from api.views.budgeting import TransactionMonthsView
from tests.helpers import B

pytestmark = pytest.mark.django_db

LOGGER = "api.requests"


def _api_lines(caplog):
    return [r for r in caplog.records if r.name == LOGGER]


def test_authenticated_call_is_logged_with_user_status_and_request_id(api, user, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    r = api.get(B + "/transactions/", {"month": "2026-11"})
    assert r.status_code == 200
    [rec] = _api_lines(caplog)
    assert rec.levelno == logging.INFO
    msg = rec.getMessage()
    assert msg.startswith("GET /api/v1/budgeting/transactions/?month=2026-11 200 ")
    assert f"user={user.pk}" in msg
    assert rec.status_code == 200 and rec.duration_ms >= 0
    # The id in the response header is the one on the log line.
    assert r["X-Request-ID"] and rec.request_id == r["X-Request-ID"]


def test_secret_and_personal_query_values_are_masked(api, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    api.get(B + "/transactions/", {"month": "2026-11", "token": "s3cret-token", "email": "a@b.com"})
    msg = _api_lines(caplog)[0].getMessage()
    assert "s3cret-token" not in msg and "a@b.com" not in msg
    assert "token=***" in msg and "email=***" in msg
    assert "month=2026-11" in msg


def test_failed_and_anonymous_calls_are_warnings(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    r = APIClient().get(B + "/transactions/")
    assert r.status_code == 401
    [rec] = _api_lines(caplog)
    assert rec.levelno == logging.WARNING
    assert " 401 " in rec.getMessage() and "user=anon" in rec.getMessage()


def test_server_errors_are_logged_as_errors(user, monkeypatch, caplog):
    def boom(self, request):
        raise RuntimeError("boom")

    monkeypatch.setattr(TransactionMonthsView, "get", boom)
    client = APIClient(raise_request_exception=False)
    client.force_authenticate(user)
    caplog.set_level(logging.INFO, logger=LOGGER)
    r = client.get(B + "/transactions/months/")
    assert r.status_code == 500
    [rec] = _api_lines(caplog)
    assert rec.levelno == logging.ERROR and " 500 " in rec.getMessage()


def test_slow_calls_are_warnings(api, settings, caplog):
    settings.API_LOG_SLOW_MS = 0
    caplog.set_level(logging.INFO, logger=LOGGER)
    api.get(B + "/transactions/")
    [rec] = _api_lines(caplog)
    assert rec.levelno == logging.WARNING and rec.getMessage().endswith(" slow")


def test_incoming_request_id_is_kept_only_when_safe(api, caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    r = api.get(B + "/transactions/", HTTP_X_REQUEST_ID="web-abc12345")
    assert r["X-Request-ID"] == "web-abc12345"
    r = api.get(B + "/transactions/", HTTP_X_REQUEST_ID="bad id\nforged log line")
    assert r["X-Request-ID"] != "bad id\nforged log line"
    assert "forged" not in r["X-Request-ID"]


def test_health_checks_are_not_logged(caplog):
    caplog.set_level(logging.INFO, logger=LOGGER)
    APIClient().get("/api/v1/health/")
    APIClient().get("/healthz/")
    assert _api_lines(caplog) == []


def test_other_loggers_get_the_request_id(api, monkeypatch):
    seen = {}

    def spy(self, request):
        record = logging.LogRecord("x", logging.INFO, __file__, 0, "inside", None, None)
        RequestIdFilter().filter(record)
        seen["id"] = record.request_id
        from rest_framework.response import Response
        return Response([])

    monkeypatch.setattr(TransactionMonthsView, "get", spy)
    r = api.get(B + "/transactions/months/")
    assert seen["id"] == r["X-Request-ID"]
    outside = logging.LogRecord("x", logging.INFO, __file__, 0, "outside", None, None)
    RequestIdFilter().filter(outside)
    assert outside.request_id == "-"
