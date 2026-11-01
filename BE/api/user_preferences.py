"""Load/save per-user locale preferences (Firestore)."""
from api.locale_defaults import detect_locale_defaults, _normalize_currency
from api.utils import user_id
from budgeting.store import UserPreferencesFS


def get_user_preferences(user) -> dict:
    uid = user_id(user)
    prefs = UserPreferencesFS.get_for_user(uid)
    if not prefs:
        return {"timezone": "", "country": "", "default_currency": "USD"}
    return {
        "timezone": prefs.timezone or "",
        "country": prefs.country or "",
        "default_currency": _normalize_currency(prefs.default_currency),
    }


def save_user_preferences(user, data: dict) -> dict:
    uid = user_id(user)
    prefs = UserPreferencesFS.get_for_user(uid) or UserPreferencesFS(pk=uid, user_id=uid)
    merged = detect_locale_defaults(
        timezone=data.get("timezone") if "timezone" in data else prefs.timezone,
        locale=None,
        country=data.get("country") if "country" in data else prefs.country,
        default_currency=data.get("default_currency") if "default_currency" in data else prefs.default_currency,
    )
    prefs.timezone = merged["timezone"]
    prefs.country = merged["country"]
    prefs.default_currency = merged["default_currency"]
    prefs.save()
    return get_user_preferences(user)


def ensure_user_preferences(user, *, timezone=None, locale=None, country=None) -> dict:
    """Create or refresh preferences from client hints when not yet saved."""
    uid = user_id(user)
    existing = UserPreferencesFS.get_for_user(uid)
    if existing and existing.default_currency and existing.timezone:
        return get_user_preferences(user)
    detected = detect_locale_defaults(timezone=timezone, locale=locale, country=country)
    if existing:
        if not existing.timezone and detected["timezone"]:
            existing.timezone = detected["timezone"]
        if not existing.country and detected["country"]:
            existing.country = detected["country"]
        if not existing.default_currency or existing.default_currency == "USD":
            if detected["default_currency"] != "USD" or not existing.default_currency:
                existing.default_currency = detected["default_currency"]
        existing.save()
    else:
        UserPreferencesFS(
            pk=uid,
            user_id=uid,
            timezone=detected["timezone"],
            country=detected["country"],
            default_currency=detected["default_currency"],
        ).save()
    return get_user_preferences(user)
