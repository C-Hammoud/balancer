"""
Category visibility: each user sees the shared defaults (user_id "") plus their own.
Only staff may change shared defaults; users may change only what they own.
"""
from .store import CategoryFS, GroupFS


def _uid(user) -> str:
    return str(user.pk) if hasattr(user, "pk") else str(user or "")


def is_visible(obj, user) -> bool:
    owner = getattr(obj, "user_id", "") or ""
    return not owner or owner == _uid(user)


def can_edit(obj, user) -> bool:
    owner = getattr(obj, "user_id", "") or ""
    if owner:
        return owner == _uid(user)
    return bool(getattr(user, "is_staff", False))


def visible_groups(user) -> list:
    return [g for g in GroupFS.list_all(limit=2000) if is_visible(g, user)]


def visible_categories(user) -> list:
    return [c for c in CategoryFS.list_all(limit=5000) if is_visible(c, user)]


def get_visible_group(user, pk):
    g = GroupFS.get(pk) if pk else None
    return g if g and is_visible(g, user) else None


def get_visible_category(user, pk):
    c = CategoryFS.get(pk) if pk else None
    return c if c and is_visible(c, user) else None
