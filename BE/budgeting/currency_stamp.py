"""
Record the currency on saved amounts that have none (budget lines, savings months, net-worth
snapshots). Older rows were saved without a currency and were read as "the main currency",
so changing the main currency silently changed what they meant.

Only blank currencies are filled: amounts are never changed and nothing is deleted.
"""
from api.locale_defaults import VALID_CURRENCIES

from .store import BudgetFS, FinancialStandingFS, SavingsFS

# Enough for every row a user can have (list_by_user caps results).
_ALL = 100_000

KINDS = (
    ("budgets", lambda uid: BudgetFS.list_by_user(uid, limit=_ALL)),
    ("savings", lambda uid: SavingsFS.list_by_user(uid, limit=_ALL)),
    ("net_worth", lambda uid: FinancialStandingFS.list_by_user(uid, limit=_ALL)),
)


def stamp_blank_currency(uid: str, currency: str, *, dry_run: bool = False) -> dict:
    """Set `currency` on this user's rows that have none. Returns {kind: rows stamped}."""
    code = (currency or "").strip().upper()
    if code not in VALID_CURRENCIES:
        raise ValueError(f"Unknown currency: {currency}")
    counts = {}
    for kind, load in KINDS:
        n = 0
        for row in load(str(uid)):
            if (getattr(row, "currency", "") or "").strip():
                continue
            n += 1
            if not dry_run:
                row.currency = code
                row.save()
        counts[kind] = n
    return counts
