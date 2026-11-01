"""
Account balances computed on the server (previously only in the mobile app, money.ts).

Rule, per account and per currency:
  income  -> +amount on the account (pending income is ignored until it settles)
  expense -> -amount on the account (pending expenses count: the money is committed)
  transfer with to_account_id -> -amount on the source account, +amount on to_account_id
  legacy transfer (two rows, no to_account_id) -> "transfer from ..." adds, anything else subtracts
"""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List, Optional

from api.currency import convert_amount

from .services import _user_id, counts_as_income
from .store import IncomeSourceFS, TransactionFS

ZERO = Decimal("0")
LIQUID_TYPES = ("bank", "wallet", "other")
# Transactions recorded without an account (older data, commitment payments) or on an account
# that was deleted are still the user's money: they are kept under this key.
UNASSIGNED = ""


def _add(balances: Dict[str, Dict[str, Decimal]], account_id: str, currency: str, amount: Decimal) -> None:
    per_currency = balances.setdefault(account_id, {})
    per_currency[currency] = per_currency.get(currency, ZERO) + amount


def raw_balances(uid: str) -> Dict[str, Dict[str, Decimal]]:
    """account_id -> {currency: balance} over all of the user's transactions."""
    return _scan(uid)[0]


def _scan(uid: str) -> tuple:
    """(balances, has_inflows). has_inflows is False when money never entered any account
    (only expenses recorded, no opening balance): the balances then only measure spending."""
    balances: Dict[str, Dict[str, Decimal]] = {}
    has_inflows = False
    for t in TransactionFS.list_all_for_user(uid):
        account_id = getattr(t, "income_source_id", "") or ""
        currency = (getattr(t, "currency", None) or "USD").upper()
        amount = t.amount or ZERO
        pending = (getattr(t, "status", "settled") or "settled") == "pending"
        if t.direction == "income":
            if counts_as_income(t):
                _add(balances, account_id, currency, amount)
                has_inflows = True
        elif t.direction == "expense":
            _add(balances, account_id, currency, -amount)
        elif t.direction == "transfer":
            to_account = getattr(t, "to_account_id", "") or ""
            if to_account:
                _add(balances, account_id, currency, -amount)
                if not pending:
                    _add(balances, to_account, currency, amount)
            elif (t.description or "").strip().lower().startswith("transfer from"):
                if not pending:
                    _add(balances, account_id, currency, amount)
                    has_inflows = True
            else:
                _add(balances, account_id, currency, -amount)
    return balances, has_inflows


def account_balances(user, report_currency: str) -> List[dict]:
    """One row per account with balances by currency and the total in report_currency."""
    return _account_rows(user, report_currency)[0]


def _account_rows(user, report_currency: str) -> tuple:
    uid = _user_id(user)
    balances, has_inflows = _scan(uid)
    rows = []
    known = set()
    for acc in IncomeSourceFS.list_by_user(uid):
        known.add(acc.pk)
        per_currency = balances.get(acc.pk, {})
        total = _convert_total(per_currency, report_currency)
        rows.append({
            "account_id": acc.pk,
            "name": acc.name,
            "account_type": getattr(acc, "account_type", "bank") or "bank",
            "is_active": bool(acc.is_active),
            "balances": {c: str(v) for c, v in sorted(per_currency.items())},
            "total": total.quantize(Decimal("0.01")),
            "currency": report_currency,
        })
    unassigned = sum(
        (_convert_total(per_currency, report_currency) for acc_id, per_currency in balances.items() if acc_id not in known),
        ZERO,
    )
    return rows, has_inflows, unassigned.quantize(Decimal("0.01"))


def _convert_total(per_currency: Dict[str, Decimal], report_currency: str) -> Decimal:
    return sum(
        (convert_amount(amount, currency, report_currency) for currency, amount in per_currency.items()),
        ZERO,
    )


def liquid_and_card_totals(user, report_currency: str, included_ids: Optional[List[str]] = None) -> dict:
    """
    Totals used by the risk engine:
      liquid    active bank/wallet/other accounts (or the accounts chosen in risk settings),
                cards holding money (positive balance) and money recorded without an account
      card_debt negative credit-card balances
    """
    rows, has_inflows, unassigned = _account_rows(user, report_currency)
    included = set(included_ids or [])
    liquid = ZERO
    card_debt = ZERO
    liquid_accounts = []
    for row in rows:
        if row["account_type"] == "credit_card":
            if row["total"] < 0:
                card_debt += -row["total"]
                continue
            # A card holding money (salary paid into it, an overpayment) is cash you can spend.
            selected = row["total"] > 0 and (row["account_id"] in included if included else row["is_active"])
        else:
            selected = row["account_id"] in included if included else row["is_active"] and row["account_type"] in LIQUID_TYPES
        if selected:
            liquid += row["total"]
            liquid_accounts.append(row["account_id"])
    if not included and unassigned:
        liquid += unassigned
    return {
        "liquid": liquid,
        "card_debt": card_debt,
        "accounts": rows,
        "liquid_account_ids": liquid_accounts,
        "has_inflows": has_inflows,
        "unassigned": unassigned,
    }
