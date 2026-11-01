"""Share personal budgets with other users by email."""
from __future__ import annotations

from typing import List, Optional

from django.contrib.auth import get_user_model
from django.utils import timezone

from api.utils import user_id
from budgeting.personal_budget_access import require_owner
from budgeting.personal_budget_constants import EDITOR, MEMBER_ROLES, VIEWER
from budgeting.store import (
    PersonalBudgetFS,
    PersonalBudgetInviteFS,
    PersonalBudgetMemberFS,
    PersonalBudgetNotificationFS,
)

User = get_user_model()


def _user_display(u) -> dict:
    name = " ".join(filter(None, [u.first_name, u.last_name])).strip() or u.username
    return {
        "id": u.pk,
        "email": u.email or "",
        "name": name,
        "username": u.username,
    }


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def lookup_user_by_email(email: str) -> Optional[dict]:
    email = _normalize_email(email)
    if not email:
        return None
    u = User.objects.filter(email__iexact=email).first()
    if not u:
        return None
    return _user_display(u)


def _pending_invites_for_budget(budget_id: str) -> List[dict]:
    return [
        {
            "id": inv.pk,
            "email": inv.email,
            "role": inv.role,
            "pending": True,
            "created_at": inv.created_at.isoformat() if inv.created_at else None,
        }
        for inv in PersonalBudgetInviteFS.list_by_budget(budget_id)
    ]


def list_budget_members(owner, budget_id: str) -> dict:
    budget = require_owner(owner, budget_id)
    owner_user = User.objects.filter(pk=int(budget.user_id)).first()
    members = []
    for m in PersonalBudgetMemberFS.list_by_budget(budget_id):
        u = User.objects.filter(pk=int(m.user_id)).first()
        if not u:
            continue
        members.append({
            "id": m.pk,
            "user_id": m.user_id,
            "email": u.email or "",
            "name": _user_display(u)["name"],
            "role": m.role,
            "pending": False,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })
    return {
        "owner": _user_display(owner_user) if owner_user else {"id": budget.user_id, "email": "", "name": ""},
        "members": members,
        "pending_invites": _pending_invites_for_budget(budget_id),
    }


def _grant_member_and_notify(*, owner, target, budget, budget_id: str, role: str) -> None:
    from api.emails import send_budget_shared_email

    member = PersonalBudgetMemberFS(
        budget_id=budget_id,
        user_id=str(target.pk),
        role=role,
    )
    member.save()
    sharer_name = _user_display(owner)["name"]
    perm_label = "Viewer" if role == VIEWER else "Editor"
    PersonalBudgetNotificationFS(
        recipient_id=str(target.pk),
        budget_id=budget_id,
        shared_by_id=user_id(owner),
        role=role,
        title=f'{sharer_name} shared "{budget.name}" with you',
        message=f"Permission: {perm_label}",
    ).save()
    send_budget_shared_email(
        recipient=target,
        shared_by=owner,
        budget_name=budget.name,
        budget_id=budget_id,
        role=role,
    )


def share_with_registered_user(owner, budget_id: str, email: str, role: str) -> dict:
    if role not in MEMBER_ROLES:
        raise ValueError("Invalid permission. Choose Viewer or Editor.")
    budget = require_owner(owner, budget_id)
    email_norm = _normalize_email(email)
    target = User.objects.filter(email__iexact=email_norm).first()
    if not target:
        raise LookupError("user_not_found")
    if str(target.pk) == user_id(owner):
        raise ValueError("You already own this budget.")
    existing = PersonalBudgetMemberFS.get_for_budget_user(budget_id, str(target.pk))
    if existing:
        raise ValueError("This user already has access to this budget.")
    pending = PersonalBudgetInviteFS.get_for_budget_email(budget_id, email_norm)
    if pending:
        pending.delete()
    _grant_member_and_notify(owner=owner, target=target, budget=budget, budget_id=budget_id, role=role)
    data = list_budget_members(owner, budget_id)
    data["result"] = "shared"
    return data


def invite_external_user(owner, budget_id: str, email: str, role: str) -> dict:
    from api.emails import send_budget_invite_email

    if role not in MEMBER_ROLES:
        raise ValueError("Invalid permission. Choose Viewer or Editor.")
    budget = require_owner(owner, budget_id)
    email_norm = _normalize_email(email)
    if not email_norm:
        raise ValueError("Email is required.")
    owner_email = _normalize_email(getattr(owner, "email", "") or "")
    if email_norm == owner_email:
        raise ValueError("You already own this budget.")
    if User.objects.filter(email__iexact=email_norm).exists():
        raise ValueError("This email belongs to a registered user. Share directly instead.")
    existing_invite = PersonalBudgetInviteFS.get_for_budget_email(budget_id, email_norm)
    if existing_invite:
        existing_invite.role = role
        existing_invite.invited_by_id = user_id(owner)
        existing_invite.save()
        invite = existing_invite
    else:
        invite = PersonalBudgetInviteFS(
            budget_id=budget_id,
            email=email_norm,
            role=role,
            invited_by_id=user_id(owner),
        )
        invite.save()
    email_sent = send_budget_invite_email(
        recipient_email=email_norm,
        shared_by=owner,
        budget_name=budget.name,
        budget_id=budget_id,
        role=role,
    )
    data = list_budget_members(owner, budget_id)
    data["result"] = "invited"
    data["email_sent"] = email_sent
    data["invited_email"] = email_norm
    return data


def share_or_invite_by_email(owner, budget_id: str, email: str, role: str) -> dict:
    """Share with a registered user, or send an external invitation email."""
    email_norm = _normalize_email(email)
    if User.objects.filter(email__iexact=email_norm).first():
        return share_with_registered_user(owner, budget_id, email_norm, role)
    return invite_external_user(owner, budget_id, email_norm, role)


def cancel_pending_invite(owner, budget_id: str, invite_id: str) -> dict:
    require_owner(owner, budget_id)
    invite = PersonalBudgetInviteFS.get(invite_id)
    if not invite or invite.budget_id != str(budget_id):
        raise PermissionError("Invitation not found.")
    invite.delete()
    return list_budget_members(owner, budget_id)


def accept_pending_budget_invites(user) -> int:
    """
    When a user registers or verifies email, turn pending invites into memberships.
    Returns the number of budgets granted.
    """
    email = _normalize_email(getattr(user, "email", "") or "")
    if not email:
        return 0
    count = 0
    for inv in PersonalBudgetInviteFS.list_by_email(email):
        budget = PersonalBudgetFS.get(inv.budget_id)
        if not budget:
            inv.delete()
            continue
        if PersonalBudgetMemberFS.get_for_budget_user(inv.budget_id, str(user.pk)):
            inv.delete()
            continue
        owner = User.objects.filter(pk=int(budget.user_id)).first()
        if not owner:
            inv.delete()
            continue
        _grant_member_and_notify(
            owner=owner,
            target=user,
            budget=budget,
            budget_id=inv.budget_id,
            role=inv.role,
        )
        inv.delete()
        count += 1
    return count


def update_member_role(owner, budget_id: str, member_id: str, role: str) -> dict:
    if role not in MEMBER_ROLES:
        raise ValueError("Invalid permission.")
    require_owner(owner, budget_id)
    member = PersonalBudgetMemberFS.get(member_id)
    if not member or member.budget_id != str(budget_id):
        raise PermissionError("Member not found.")
    member.role = role
    member.save()
    return list_budget_members(owner, budget_id)


def remove_member(owner, budget_id: str, member_id: str) -> dict:
    require_owner(owner, budget_id)
    member = PersonalBudgetMemberFS.get(member_id)
    if not member or member.budget_id != str(budget_id):
        raise PermissionError("Member not found.")
    member.delete()
    return list_budget_members(owner, budget_id)


def list_shared_with_me(user) -> List[dict]:
    from budgeting.personal_budget_service import serialize_budget_summary

    uid = user_id(user)
    out = []
    for m in PersonalBudgetMemberFS.list_by_user(uid):
        budget = PersonalBudgetFS.get(m.budget_id)
        if not budget:
            continue
        owner_user = User.objects.filter(pk=int(budget.user_id)).first()
        summary = serialize_budget_summary(budget, user, access_role=m.role)
        summary["is_owner"] = False
        if owner_user:
            summary["owner"] = _user_display(owner_user)
        else:
            summary["owner"] = {"id": budget.user_id, "email": "", "name": ""}
        out.append(summary)
    return out


def list_notifications(user, limit: int = 50) -> List[dict]:
    uid = user_id(user)
    rows = []
    for n in PersonalBudgetNotificationFS.list_for_recipient(uid, limit=limit):
        sharer = User.objects.filter(pk=int(n.shared_by_id)).first()
        budget = PersonalBudgetFS.get(n.budget_id)
        rows.append({
            "id": n.pk,
            "budget_id": n.budget_id,
            "budget_name": budget.name if budget else "",
            "title": n.title,
            "message": n.message or "",
            "role": n.role,
            "shared_by": _user_display(sharer) if sharer else None,
            "read": bool(n.read_at),
            "created_at": n.created_at.isoformat() if n.created_at else None,
        })
    return rows


def mark_notification_read(user, notification_id: str) -> None:
    uid = user_id(user)
    n = PersonalBudgetNotificationFS.get(notification_id)
    if not n or n.recipient_id != uid:
        raise PermissionError("Notification not found.")
    n.read_at = timezone.now()
    n.save()
