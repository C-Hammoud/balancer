"""
One log line per API call, plus a request id on every log line written while it runs.

    INFO api.requests [3f9c1a2b7d4e] GET /api/v1/budgeting/transactions/?month=2026-11 200 41ms user=12 ip=203.0.113.9

- Level follows the outcome: INFO for success, WARNING for 4xx and slow calls, ERROR for 5xx
  (Django's own "django.request" logger still writes the traceback of a server error).
- Bodies are never logged (passwords, statements, amounts), and query values that carry secrets
  or personal data (token, uid, email, …) are masked.
- The request id comes from an incoming X-Request-ID header (from Caddy or the web app) when it
  looks safe, otherwise a new one; it is sent back in the X-Request-ID response header so a
  user's report can be matched to the server log.
"""
from __future__ import annotations

import contextvars
import logging
import re
import time
import uuid
from urllib.parse import parse_qsl, urlencode

from django.conf import settings

logger = logging.getLogger("api.requests")

_request_id: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")

REQUEST_ID_HEADER = "X-Request-ID"
_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
SENSITIVE_QUERY_KEYS = frozenset({
    "token", "uid", "email", "refresh", "access", "password", "code", "key", "secret", "signature",
})
DEFAULT_LOGGED_PREFIXES = ("/api/",)
DEFAULT_SKIPPED_PATHS = ("/api/v1/health/", "/api/schema/", "/api/docs/")


def current_request_id() -> str:
    return _request_id.get()


class RequestIdFilter(logging.Filter):
    """Adds `request_id` to every record so the log format can show it ("-" outside a request)."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = _request_id.get()
        return True


def _masked_query(query_string: str) -> str:
    if not query_string:
        return ""
    pairs = parse_qsl(query_string, keep_blank_values=True)
    masked = [(k, "***" if k.lower() in SENSITIVE_QUERY_KEYS else v) for k, v in pairs]
    return "?" + urlencode(masked, safe="-_.,:/*")


def _client_ip(request) -> str:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "") or "-"


def _user_label(request) -> str:
    # DRF copies the authenticated user (JWT or session) onto the Django request.
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return str(user.pk)
    return "anon"


class ApiRequestLogMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.prefixes = tuple(getattr(settings, "API_LOG_PATH_PREFIXES", DEFAULT_LOGGED_PREFIXES))
        self.skipped = tuple(getattr(settings, "API_LOG_SKIP_PATHS", DEFAULT_SKIPPED_PATHS))
        self.slow_ms = int(getattr(settings, "API_LOG_SLOW_MS", 2000))

    def _should_log(self, path: str) -> bool:
        return path.startswith(self.prefixes) and not path.startswith(self.skipped)

    def __call__(self, request):
        incoming = request.META.get("HTTP_X_REQUEST_ID", "")
        request_id = incoming if _SAFE_REQUEST_ID.match(incoming) else uuid.uuid4().hex[:12]
        token = _request_id.set(request_id)
        request.request_id = request_id
        started = time.perf_counter()
        try:
            response = self.get_response(request)
            duration_ms = int((time.perf_counter() - started) * 1000)
            response[REQUEST_ID_HEADER] = request_id
            if self._should_log(request.path):
                self._log(request, response.status_code, duration_ms)
            return response
        finally:
            _request_id.reset(token)

    def _log(self, request, status_code: int, duration_ms: int) -> None:
        if status_code >= 500:
            level = logging.ERROR
        elif status_code >= 400 or duration_ms >= self.slow_ms:
            level = logging.WARNING
        else:
            level = logging.INFO
        logger.log(
            level,
            "%s %s%s %s %dms user=%s ip=%s%s",
            request.method,
            request.path,
            _masked_query(request.META.get("QUERY_STRING", "")),
            status_code,
            duration_ms,
            _user_label(request),
            _client_ip(request),
            " slow" if duration_ms >= self.slow_ms else "",
            extra={
                "method": request.method,
                "path": request.path,
                "status_code": status_code,
                "duration_ms": duration_ms,
            },
        )
