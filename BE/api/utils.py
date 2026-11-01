"""Shared helpers for REST API views."""
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Optional

from rest_framework_simplejwt.tokens import RefreshToken


def user_id(user) -> str:
    return str(user.pk)


def jwt_for_user(user) -> dict:
    refresh = RefreshToken.for_user(user)
    return {
        "refresh": str(refresh),
        "access": str(refresh.access_token),
    }


def trigger_budget_alerts(user, when_date: Optional[date] = None, month: Optional[int] = None, *, year: Optional[int] = None):
    """
    Re-evaluate budget alerts (forced refresh — use after data changes).
    Call as:
      trigger_budget_alerts(user)
      trigger_budget_alerts(user, some_date)
      trigger_budget_alerts(user, year, month)  # year/month as positional ints
    """
    try:
        from budgeting.alerts import refresh_alerts_for_user

        if isinstance(when_date, int) and month is not None:
            refresh_alerts_for_user(user, year=when_date, month=int(month), force=True)
            return

        y = year
        m = month
        if when_date is not None and not isinstance(when_date, int):
            y = when_date.year
            m = when_date.month
        refresh_alerts_for_user(user, year=y, month=m, force=True)
    except Exception:
        pass


def _dt(value) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _dec(value) -> str:
    if value is None:
        return "0"
    return str(value)


def consumption_to_dict(c) -> dict:
    return {
        "id": c.pk,
        "date": c.date.isoformat() if c.date else None,
        "time": getattr(c, "time", "") or "",
        "amount": _dec(c.amount),
        "currency": c.currency,
        "amount_usd": _dec(c.amount_usd),
        "consumption_type": c.consumption_type,
        "note": c.note or "",
        "country": c.country or "",
        "record_status": c.record_status,
        "created_at": _dt(c.created_at),
        "modified_at": _dt(c.modified_at),
    }


def transaction_to_dict(t) -> dict:
    return {
        "id": t.pk,
        "date": t.date.isoformat() if t.date else None,
        "time": getattr(t, "time", "") or "",
        "month": t.month,
        "description": t.description,
        "category_id": t.category_id,
        "classification": t.classification,
        "amount": _dec(t.amount),
        "currency": getattr(t, "currency", None) or "USD",
        "note": getattr(t, "note", "") or "",
        "direction": t.direction,
        "source_account": t.source_account or "",
        "account_id": getattr(t, "income_source_id", "") or "",
        "income_source_id": getattr(t, "income_source_id", "") or "",
        "commitment_id": getattr(t, "commitment_id", "") or "",
        "schedule_line_id": getattr(t, "schedule_line_id", "") or "",
        "external_id": t.external_id or "",
        "include_in_utilization": bool(getattr(t, "include_in_utilization", False)),
        "budget_id": getattr(t, "budget_id", "") or "",
        "budget_category_id": getattr(t, "budget_category_id", "") or "",
        "to_account_id": getattr(t, "to_account_id", "") or "",
        "status": getattr(t, "status", "") or "settled",
        "created_at": _dt(t.created_at),
        "updated_at": _dt(t.updated_at),
    }


def decimal_to_json(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: decimal_to_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [decimal_to_json(v) for v in value]
    return value
