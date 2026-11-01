"""
Sub-budgets: personal budgets (a trip, a project) attached to the monthly plan.

The plan's available money (income - installments) is the main budget. A sub-budget reserves its
total_amount inside it, in one month or spread over `funding_months` months from `funding_start`.
Expenses tagged to a sub-budget count only there, never in the regular category budgets.
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import FrozenSet, List, Optional

from api.currency import convert_if_needed

from .personal_budget_constants import ACTIVE, ARCHIVED, COMPLETED, DRAFT
from .services import _user_id
from .store import PersonalBudgetFS, TransactionFS

ZERO = Decimal("0")
MAX_FUNDING_MONTHS = 36
# A sub-budget keeps reserving money while it is being prepared or used.
PLANNABLE_STATUSES = (DRAFT, ACTIVE)


def _month_index(d: date) -> int:
    return d.year * 12 + d.month - 1


def _first_of_month(d: date) -> date:
    return d.replace(day=1)


def default_funding(budget, today: Optional[date] = None) -> tuple:
    """(funding_start, funding_months): from this month up to the month before the budget starts."""
    today = today or date.today()
    start = _first_of_month(today)
    if budget.start_date and _month_index(budget.start_date) > _month_index(today):
        months = _month_index(budget.start_date) - _month_index(today)
        return start, max(1, min(months, MAX_FUNDING_MONTHS))
    return start, 1


def in_plan_budgets(user) -> List:
    """Active sub-budgets owned by the user (budgets shared with them never count here)."""
    uid = _user_id(user)
    return [
        b for b in PersonalBudgetFS.list_by_user(uid, limit=1000)
        if b.in_plan and b.status in PLANNABLE_STATUSES and b.user_id == uid
    ]


def envelope_ids(user) -> FrozenSet[str]:
    """Budget ids whose expenses count only in the sub-budget (excluded from category budgets)."""
    return frozenset(str(b.pk) for b in in_plan_budgets(user))


def _schedule(budget) -> List[tuple]:
    """[(month_index, amount)] in the budget's own currency; the last month absorbs rounding."""
    months = max(1, int(budget.funding_months or 1))
    start = budget.funding_start or _first_of_month(budget.start_date or date.today())
    total = Decimal(budget.total_amount or 0)
    share = (total / months).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    first = _month_index(start)
    out = [(first + i, share) for i in range(months)]
    out[-1] = (out[-1][0], total - share * (months - 1))
    return out


def contribution_for(budget, year: int, month: int, currency: str) -> Decimal:
    """What this sub-budget reserves in the given month, in `currency`."""
    target = year * 12 + month - 1
    amount = sum((a for m, a in _schedule(budget) if m == target), ZERO)
    return convert_if_needed(amount, budget.currency or "USD", currency) if amount else ZERO


def funded_before(budget, year: int, month: int, currency: str) -> Decimal:
    target = year * 12 + month - 1
    amount = sum((a for m, a in _schedule(budget) if m < target), ZERO)
    return convert_if_needed(amount, budget.currency or "USD", currency) if amount else ZERO


def spent(budget, currency: str) -> Decimal:
    total = ZERO
    for t in TransactionFS.list_by_budget(str(budget.pk), limit=5000):
        if t.direction == "expense":
            total += convert_if_needed(t.amount or ZERO, getattr(t, "currency", None) or "USD", currency)
    return total


def plan_lines(user, year: int, month: int, currency: str) -> List[dict]:
    """Sub-budget lines reserved in the given month's plan."""
    lines = []
    for b in in_plan_budgets(user):
        amount = contribution_for(b, year, month, currency)
        if amount <= 0:
            continue
        lines.append({
            "budget_id": str(b.pk),
            "name": b.name,
            "amount": amount.quantize(Decimal("0.01")),
            "total": convert_if_needed(Decimal(b.total_amount or 0), b.currency or "USD", currency).quantize(
                Decimal("0.01")
            ),
            "funded_before": funded_before(b, year, month, currency).quantize(Decimal("0.01")),
            "spent": spent(b, currency).quantize(Decimal("0.01")),
            "start_date": b.start_date.isoformat() if b.start_date else None,
            "end_date": b.end_date.isoformat() if b.end_date else None,
            "funding_months": int(b.funding_months or 1),
        })
    lines.sort(key=lambda line: line["name"].lower())
    return lines


def attach_error(user, budget) -> Optional[str]:
    if budget.user_id != _user_id(user):
        return "Only the owner can add a budget to their plan."
    if budget.is_default:
        return "The default budget cannot be added to a plan."
    if budget.status in (ARCHIVED, COMPLETED):
        return "Archived or completed budgets cannot be added to a plan."
    return None


def attach(user, budget, funding_months: Optional[int] = None, funding_start: Optional[date] = None):
    """Make the budget a sub-budget of the user's plans. Raises ValueError with a user message."""
    error = attach_error(user, budget)
    if error:
        raise ValueError(error)
    default_start, default_months = default_funding(budget)
    budget.in_plan = True
    budget.funding_start = _first_of_month(funding_start) if funding_start else default_start
    budget.funding_months = max(1, min(int(funding_months or default_months), MAX_FUNDING_MONTHS))
    budget.save()
    return budget


def detach(user, budget):
    if budget.user_id != _user_id(user):
        raise ValueError("Only the owner can remove a budget from their plan.")
    budget.in_plan = False
    budget.save()
    return budget


def monthly_contribution(budget, today: Optional[date] = None) -> Decimal:
    """This month's share in the budget's own currency (for the budget summary)."""
    today = today or date.today()
    if not budget.in_plan:
        return ZERO
    target = _month_index(today)
    return sum((a for m, a in _schedule(budget) if m == target), ZERO)
