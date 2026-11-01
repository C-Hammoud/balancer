"""
Alert lifecycle helpers shared by the SQLite and Firestore stores (no store imports here).
"""
from datetime import datetime, timezone as dt_timezone
from typing import Optional

from django.utils import timezone

RESOLUTION_USER = "user"
RESOLUTION_AUTO = "auto"


def _aware(value: datetime) -> datetime:
    if timezone.is_naive(value):
        return timezone.make_aware(value, dt_timezone.utc)
    return value


def alert_is_snoozed(alert, now: Optional[datetime] = None) -> bool:
    until = getattr(alert, "snoozed_until", None)
    if not until or getattr(alert, "is_resolved", False):
        return False
    return _aware(until) > _aware(now or timezone.now())


def alert_state(alert, now: Optional[datetime] = None) -> str:
    """open | snoozed | resolved"""
    if alert.is_resolved:
        return "resolved"
    if alert_is_snoozed(alert, now):
        return "snoozed"
    return "open"
