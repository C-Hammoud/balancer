"""
Who a campaign goes to. An audience is a dict:
  {"type": "all"}                                     every active user
  {"type": "users", "user_ids": [1, 2]}               hand-picked users (active ones)
  {"type": "filter", "flags": [...], "countries": [...], "currencies": [...],
   "verified": "yes"|"no", "joined_from": "YYYY-MM-DD", "joined_to": "YYYY-MM-DD",
   "last_login": "never"|"30"|"90"|"180"}             active users matching every filter given
Flags match when the user has any of them.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Tuple

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from api import support

User = get_user_model()

TYPES = ("all", "filter", "users")
AUDIENCE_FLAGS = ("email_unverified", "setup_stuck", "no_activity", "email_failed", "open_ticket")
STORE_FLAGS = ("no_activity",)  # need the budgeting store, checked per user
MAX_USER_IDS = 5000


def clean_audience(raw) -> Tuple[dict, Dict[str, List[str]]]:
    """Validated audience (unknown keys dropped) and errors per field."""
    raw = raw if isinstance(raw, dict) else {}
    errors: Dict[str, List[str]] = {}
    kind = raw.get("type") or "filter"
    if kind not in TYPES:
        errors["type"] = ["Use all, filter or users."]
        return {}, errors
    out: dict = {"type": kind}
    if kind == "users":
        ids = raw.get("user_ids") or []
        try:
            ids = sorted({int(i) for i in ids})
        except (TypeError, ValueError):
            errors["user_ids"] = ["Use a list of user ids."]
            ids = []
        if not ids and "user_ids" not in errors:
            errors["user_ids"] = ["Pick at least one user."]
        if len(ids) > MAX_USER_IDS:
            errors["user_ids"] = [f"Pick at most {MAX_USER_IDS} users."]
        out["user_ids"] = ids
        return out, errors
    if kind == "all":
        return out, errors

    flags = [str(f) for f in (raw.get("flags") or [])]
    bad = sorted(set(flags) - set(AUDIENCE_FLAGS))
    if bad:
        errors["flags"] = [f"Unknown flag: {', '.join(bad)}."]
    out["flags"] = [f for f in AUDIENCE_FLAGS if f in flags]
    out["countries"] = sorted({str(c).strip().upper() for c in (raw.get("countries") or []) if str(c).strip()})
    out["currencies"] = sorted({str(c).strip().upper() for c in (raw.get("currencies") or []) if str(c).strip()})
    verified = (raw.get("verified") or "").strip()
    if verified not in ("", "yes", "no"):
        errors["verified"] = ["Use yes or no."]
    out["verified"] = verified
    for key in ("joined_from", "joined_to"):
        value = (raw.get(key) or "").strip()
        if value:
            try:
                date.fromisoformat(value)
            except ValueError:
                errors[key] = ["Use a date like 2026-01-31."]
        out[key] = value
    last = str(raw.get("last_login") or "").strip()
    if last not in ("", "never", *support.LAST_LOGIN_DAYS):
        errors["last_login"] = ["Use never, 30, 90 or 180."]
    out["last_login"] = last
    return out, errors


def _prefs(user) -> dict:
    from api.user_preferences import get_user_preferences

    try:
        return get_user_preferences(user)
    except Exception:
        return {}


def _no_activity(user, now) -> bool:
    joined = user.date_joined or now
    return now - joined >= support.NO_ACTIVITY_AFTER and not support.has_transactions(str(user.pk))


def audience_users(audience: dict) -> List:
    """Active users in the audience (audience must come from clean_audience), by id."""
    qs = support.annotate_users(User.objects.filter(is_active=True)).order_by("pk")
    kind = audience.get("type")
    if kind == "users":
        return list(qs.filter(pk__in=audience.get("user_ids") or []))
    if kind == "all":
        return list(qs)

    qs, _ = support.apply_user_filters(qs, {
        "verified": audience.get("verified", ""),
        "joined_from": audience.get("joined_from", ""),
        "joined_to": audience.get("joined_to", ""),
        "last_login": audience.get("last_login", ""),
    })
    qs = qs.order_by("pk")
    flags = audience.get("flags") or []
    db_flags = [f for f in flags if f not in STORE_FLAGS]
    store_flags = [f for f in flags if f in STORE_FLAGS]
    db_match = set()
    if db_flags:
        cond = Q()
        for f in db_flags:
            cond |= support._db_flag_q(f)
        db_match = set(qs.filter(cond).values_list("pk", flat=True))

    countries = set(audience.get("countries") or [])
    currencies = set(audience.get("currencies") or [])
    now = timezone.now()
    out = []
    for u in qs:
        if flags:
            hit = u.pk in db_match or ("no_activity" in store_flags and _no_activity(u, now))
            if not hit:
                continue
        if countries or currencies:
            prefs = _prefs(u)
            if countries and (prefs.get("country") or "").upper() not in countries:
                continue
            if currencies and (prefs.get("default_currency") or "").upper() not in currencies:
                continue
        out.append(u)
    return out
