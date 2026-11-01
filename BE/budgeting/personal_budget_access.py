"""Access control for personal budgets (owner / viewer / editor)."""
from __future__ import annotations

from typing import Optional, Tuple

from api.utils import user_id
from budgeting.personal_budget_constants import EDITOR, VIEWER
from budgeting.store import PersonalBudgetFS, PersonalBudgetMemberFS

OWNER = "owner"


def member_role(user, budget_id: str) -> Optional[str]:
    """Return viewer or editor if user is a member; None if not."""
    uid = user_id(user)
    member = PersonalBudgetMemberFS.get_for_budget_user(budget_id, uid)
    if not member:
        return None
    return member.role if member.role in (VIEWER, EDITOR) else VIEWER


def is_owner(user, budget: PersonalBudgetFS) -> bool:
    return str(budget.user_id) == user_id(user)


def resolve_access(user, budget_id: str) -> Tuple[Optional[PersonalBudgetFS], Optional[str]]:
    """
    Return (budget, role) where role is owner, viewer, or editor.
    Returns (None, None) if no access.
    """
    budget = PersonalBudgetFS.get(budget_id)
    if not budget:
        return None, None
    if is_owner(user, budget):
        return budget, OWNER
    role = member_role(user, budget_id)
    if role:
        return budget, role
    return None, None


def require_view(user, budget_id: str) -> Tuple[PersonalBudgetFS, str]:
    budget, role = resolve_access(user, budget_id)
    if not budget or not role:
        raise PermissionError("Budget not found.")
    return budget, role


def require_edit(user, budget_id: str) -> Tuple[PersonalBudgetFS, str]:
    budget, role = require_view(user, budget_id)
    if role not in (OWNER, EDITOR):
        raise PermissionError("You do not have permission to edit this budget.")
    return budget, role


def require_owner(user, budget_id: str) -> PersonalBudgetFS:
    budget, role = require_view(user, budget_id)
    if role != OWNER:
        raise PermissionError("Only the budget owner can perform this action.")
    return budget


def can_edit(role: str) -> bool:
    return role in (OWNER, EDITOR)
