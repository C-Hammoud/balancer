"""
Detect default country, timezone, and currency from client hints.
Used to pre-fill multi-currency forms in the Angular app.
"""
from api.constants import COUNTRIES, COUNTRY_TO_CURRENCY, CURRENCY_CHOICES, DEFAULT_CURRENCY, TZ_TO_COUNTRY

VALID_CURRENCIES = {code for code, _ in CURRENCY_CHOICES}
VALID_COUNTRIES = {code for code, _ in COUNTRIES.choices}

# IANA timezone → default currency (when country mapping is ambiguous)
TZ_TO_CURRENCY = {
    "Asia/Beirut": "LBP",
    "Asia/Riyadh": "SAR",
    "Asia/Dubai": "SAR",
    "America/New_York": "USD",
    "America/Los_Angeles": "USD",
    "Europe/London": "USD",
    "UTC": "USD",
}

# BCP-47 locale region → country (ISO 3166-1 alpha-2)
LOCALE_REGION_TO_COUNTRY = {
    "LB": COUNTRIES.LB,
    "SA": COUNTRIES.SA,
    "US": "US",
    "GB": "US",  # no GBP in app yet; fall back via currency_for_country
    "AE": COUNTRIES.SA,
}


def _normalize_currency(code: str | None) -> str:
    c = (code or "").strip().upper()
    return c if c in VALID_CURRENCIES else DEFAULT_CURRENCY


def currency_for_country(country_code: str | None) -> str:
    cc = (country_code or "").strip().upper()
    if cc in COUNTRY_TO_CURRENCY:
        return COUNTRY_TO_CURRENCY[cc]
    if cc == "US":
        return "USD"
    return DEFAULT_CURRENCY


def country_from_locale(locale: str | None) -> str:
    loc = (locale or "").strip().replace("_", "-")
    if not loc:
        return ""
    parts = loc.split("-")
    if len(parts) >= 2:
        region = parts[-1].upper()
        if region in LOCALE_REGION_TO_COUNTRY:
            return LOCALE_REGION_TO_COUNTRY[region]
        if region in VALID_COUNTRIES:
            return region
    return ""


def detect_locale_defaults(
    *,
    timezone: str | None = None,
    locale: str | None = None,
    country: str | None = None,
    default_currency: str | None = None,
) -> dict:
    """
    Merge client hints into timezone, country, and default_currency.
    Saved user preferences override detection when provided.
    """
    tz = (timezone or "").strip()
    cc = (country or "").strip().upper()
    cur = _normalize_currency(default_currency) if default_currency else ""

    if not cc and tz in TZ_TO_COUNTRY:
        cc = TZ_TO_COUNTRY[tz]
    if not cc:
        cc = country_from_locale(locale)

    if not cur:
        if tz in TZ_TO_CURRENCY:
            cur = TZ_TO_CURRENCY[tz]
        elif cc:
            cur = currency_for_country(cc)
        else:
            cur = DEFAULT_CURRENCY

    if not tz and cc:
        from api.constants import COUNTRY_TO_TZ

        tz = COUNTRY_TO_TZ.get(cc, "")

    return {
        "timezone": tz,
        "country": cc,
        "default_currency": _normalize_currency(cur),
    }
