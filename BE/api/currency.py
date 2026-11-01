"""Convert amounts between supported currencies using EXCHANGE_RATES (multiplier to USD)."""
from decimal import Decimal

from django.conf import settings

from api.locale_defaults import VALID_CURRENCIES, _normalize_currency


def get_exchange_rates() -> dict[str, float]:
    raw = getattr(settings, "EXCHANGE_RATES", None) or {}
    rates = {"USD": 1.0}
    for code, val in raw.items():
        try:
            rates[str(code).upper()] = float(val)
        except (TypeError, ValueError):
            continue
    return rates


def convert_amount(amount, from_currency: str, to_currency: str) -> Decimal:
    """Convert amount from one currency to another via USD base rates."""
    amt = Decimal(str(amount or 0))
    src = _normalize_currency(from_currency or "USD")
    dst = _normalize_currency(to_currency or "USD")
    if src == dst:
        return amt.quantize(Decimal("0.01"))
    rates = get_exchange_rates()
    src_rate = Decimal(str(rates.get(src, 1 if src == "USD" else 0)))
    dst_rate = Decimal(str(rates.get(dst, 1 if dst == "USD" else 0)))
    if src_rate <= 0 or dst_rate <= 0:
        return amt.quantize(Decimal("0.01"))
    usd = amt * src_rate
    return (usd / dst_rate).quantize(Decimal("0.01"))


def convert_if_needed(amount, from_currency: str, report_currency: str | None) -> Decimal:
    if not report_currency:
        return Decimal(str(amount or 0))
    return convert_amount(amount, from_currency or "USD", report_currency)


def resolve_report_currency(user, query_value: str | None = None) -> str:
    """Saved user default, optional query override."""
    if query_value:
        q = _normalize_currency(query_value)
        if q in VALID_CURRENCIES:
            return q
    from api.user_preferences import get_user_preferences

    return get_user_preferences(user).get("default_currency") or "USD"
