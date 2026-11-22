"""What a user has not filled in yet: the admin checklist and the {missing_items} placeholder."""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import List

from api.models import UserProfile
from api.user_profile import get_user_profile

logger = logging.getLogger(__name__)

RECENT_DAYS = 7


def _item(code: str, text: str, link: str) -> dict:
    return {"code": code, "text": text, "link": link}


def missing_items(user) -> List[dict]:
    """
    Checklist of missing data, most important first. Reads the budgeting store (SQLite or
    Firestore); a store error only drops the store-based items.
    """
    items: List[dict] = []
    profile = get_user_profile(user)
    if not profile.email_verified and (user.email or "").strip():
        items.append(_item("email_unverified", "Verify your email address", "/profile"))
    if profile.setup_status != UserProfile.SETUP_COMPLETE:
        items.append(_item("setup_incomplete", "Finish setting up your account", "/dashboard"))

    uid = str(user.pk)
    try:
        from budgeting.store import BudgetFS, CommitmentFS, IncomeSourceFS, TransactionFS

        if not IncomeSourceFS.list_by_user(uid, active_only=True, limit=1):
            items.append(_item("no_account", "Add the bank accounts, cards or wallets you pay from",
                               "/budgeting/config/accounts"))
        today = date.today()
        if not BudgetFS.list_by_user(uid, year=today.year, month=today.month, limit=1):
            items.append(_item("no_budget", "Set your budget for this month", "/budgeting/monthly-budget"))

        txns = TransactionFS.list_all_for_user(uid)
        since = today - timedelta(days=RECENT_DAYS)
        if not any(t.date and t.date >= since for t in txns):
            items.append(_item("no_recent_transactions",
                               f"Add your transactions from the last {RECENT_DAYS} days", "/budgeting/transactions"))
        unassigned = sum(
            1 for t in txns if t.direction == "expense" and not t.commitment_id and not (t.category_id or "")
        )
        if unassigned:
            items.append(_item("unassigned_transactions",
                               f"Choose a category for {unassigned} transaction{'s' if unassigned != 1 else ''}",
                               "/budgeting/transactions/assign"))
        no_category = sum(1 for c in CommitmentFS.list_by_user(uid, limit=500) if not (c.category_id or ""))
        if no_category:
            items.append(_item("commitments_without_category",
                               f"Choose a category for {no_category} commitment{'s' if no_category != 1 else ''}",
                               "/budgeting/commitments"))
    except Exception as exc:  # the budgeting store being unavailable must not break messaging
        logger.warning("Could not compute missing data for user %s: %s", uid, exc)
    return items
