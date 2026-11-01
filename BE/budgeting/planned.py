"""
Planned items: expected future money in or out (rent, subscriptions, a one-off bill or payment).
Used by the risk engine to project this month's cash flow.
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Iterable, List

from api.currency import convert_if_needed

from .commitment_schedule import add_months
from .services import _user_id
from .store import PlannedItemFS

ZERO = Decimal("0")
KINDS = ("income", "expense")
FREQUENCIES = ("once", "weekly", "biweekly", "monthly", "yearly")
_STEP_DAYS = {"weekly": 7, "biweekly": 14}
_STEP_MONTHS = {"monthly": 1, "yearly": 12}
# Monthly equivalent of one occurrence ("once" has none).
_PER_MONTH = {
    "weekly": Decimal("52") / Decimal("12"),
    "biweekly": Decimal("26") / Decimal("12"),
    "monthly": Decimal("1"),
    "yearly": Decimal("1") / Decimal("12"),
}


def occurrences(item, start: date, end: date) -> List[date]:
    """Dates in [start, end] when the item happens. Monthly/yearly dates keep the start day,
    clamped to the month's last day (Jan 31 -> Feb 28/29 -> Mar 31)."""
    first = item.start_date
    if not first or end < start:
        return []
    last = min(end, item.end_date) if item.end_date else end
    freq = item.frequency or "monthly"
    if freq == "once":
        return [first] if start <= first <= last else []
    out = []
    if freq in _STEP_DAYS:
        step = _STEP_DAYS[freq]
        d = first
        if d < start:
            d += timedelta(days=((start - d).days + step - 1) // step * step)
        while d <= last:
            out.append(d)
            d += timedelta(days=step)
        return out
    step = _STEP_MONTHS.get(freq, 1)
    n = 0
    if first < start:
        n = max(0, ((start.year - first.year) * 12 + start.month - first.month) // step - 1)
    while True:
        d = add_months(first, n * step)
        if d > last:
            break
        if d >= start:
            out.append(d)
        n += 1
    return out


def monthly_amount(item) -> Decimal:
    return Decimal(item.amount or 0) * _PER_MONTH.get(item.frequency or "monthly", ZERO)


def active_items(user, kind: str = "") -> List:
    rows = [i for i in PlannedItemFS.list_by_user(_user_id(user), limit=1000) if i.is_active]
    return [i for i in rows if i.kind == kind] if kind else rows


def total_between(items: Iterable, start: date, end: date, currency: str) -> tuple:
    """(total, contributing items) of occurrences in [start, end], converted to currency."""
    total, contributing = ZERO, []
    for item in items:
        dates = occurrences(item, start, end)
        if not dates:
            continue
        amount = convert_if_needed(Decimal(item.amount or 0) * len(dates), item.currency or "USD", currency)
        total += amount
        contributing.append({
            "id": item.pk, "name": item.name, "kind": item.kind, "amount": amount,
            "dates": [d.isoformat() for d in dates], "is_essential": bool(item.is_essential),
        })
    return total, contributing


def recurring_monthly_total(items: Iterable, currency: str) -> Decimal:
    return sum(
        (convert_if_needed(monthly_amount(i), i.currency or "USD", currency) for i in items),
        ZERO,
    )


def item_to_dict(item) -> dict:
    return {
        "id": item.pk,
        "name": item.name,
        "kind": item.kind,
        "amount": str(Decimal(item.amount or 0).quantize(Decimal("0.01"))),
        "currency": item.currency,
        "frequency": item.frequency,
        "start_date": item.start_date.isoformat() if item.start_date else None,
        "end_date": item.end_date.isoformat() if item.end_date else None,
        "account_id": item.account_id or "",
        "category_id": item.category_id or "",
        "is_essential": bool(item.is_essential),
        "is_active": bool(item.is_active),
        "monthly_amount": str(monthly_amount(item).quantize(Decimal("0.01"))),
    }
