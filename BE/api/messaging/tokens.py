"""Signed tokens in message links: email button clicks and marketing unsubscribe."""
from __future__ import annotations

from typing import Optional

from django.conf import settings
from django.core import signing

_CLICK_SALT = "messaging.click"
_UNSUBSCRIBE_SALT = "messaging.unsubscribe"


def _frontend() -> str:
    return getattr(settings, "FRONTEND_URL", "http://localhost:4200").rstrip("/")


def click_token(delivery_id: int) -> str:
    return signing.dumps({"d": int(delivery_id)}, salt=_CLICK_SALT)


def read_click_token(token: str) -> Optional[int]:
    try:
        return int(signing.loads(token, salt=_CLICK_SALT)["d"])
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return None


def click_url(delivery_id: int) -> str:
    """App page that records the click, then opens the message's link."""
    return f"{_frontend()}/m/{click_token(delivery_id)}"


def unsubscribe_token(user_id: int) -> str:
    return signing.dumps({"u": int(user_id)}, salt=_UNSUBSCRIBE_SALT)


def read_unsubscribe_token(token: str) -> Optional[int]:
    try:
        return int(signing.loads(token, salt=_UNSUBSCRIBE_SALT)["u"])
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        return None


def unsubscribe_url(user_id: int) -> str:
    return f"{_frontend()}/unsubscribe/{unsubscribe_token(user_id)}"
