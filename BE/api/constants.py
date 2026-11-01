"""Shared locale and expense-type constants (formerly in expenses app)."""

from django.db import models


class Currency(models.TextChoices):
    USD = "USD", "US Dollar"
    LBP = "LBP", "Lebanese Lira"
    SAR = "SAR", "Saudi Riyal"


class Countries(models.TextChoices):
    LB = "LB", "Lebanon"
    SA = "SA", "Saudi Arabia"


# Backward-compatible alias
COUNTRIES = Countries

CURRENCY_CHOICES = list(Currency.choices)

TYPE_CHOICES = [
    ("market", "Market"),
    ("transport", "Transport"),
    ("food", "Food"),
    ("other", "Other"),
]

TZ_TO_COUNTRY = {
    "Asia/Beirut": Countries.LB,
    "Asia/Riyadh": Countries.SA,
}

COUNTRY_TO_TZ = {
    Countries.LB: "Asia/Beirut",
    Countries.SA: "Asia/Riyadh",
}

COUNTRY_TO_CURRENCY = {
    Countries.LB: Currency.LBP,
    Countries.SA: Currency.SAR,
}

DEFAULT_CURRENCY = Currency.USD
