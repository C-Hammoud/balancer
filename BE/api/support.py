"""
Customer support: staff permissions, automatic issue flags, audit log and ticket helpers.

Roles: user.is_staff = support admin; user.is_superuser = can also grant/remove the admin role
(superusers are always treated as staff).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone as dt_timezone
from typing import Dict, List, Optional

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db.models import Exists, OuterRef, Q
from django.utils import timezone
from rest_framework.permissions import BasePermission

from api.models import AdminAuditLog, EmailLog, SupportMessage, SupportTicket, UserProfile

logger = logging.getLogger(__name__)
User = get_user_model()

UNVERIFIED_AFTER = timedelta(hours=24)
SETUP_STUCK_AFTER = timedelta(days=3)
NO_ACTIVITY_AFTER = timedelta(days=7)
EMAIL_FAILED_WINDOW = timedelta(days=7)

# code -> (severity, text). Severity drives the colour in the admin screens.
FLAGS: Dict[str, tuple] = {
    "deactivated": ("high", "Account is deactivated"),
    "email_failed": ("high", "An email to this user failed in the last 7 days"),
    "open_ticket": ("high", "Has a ticket waiting for support"),
    "high_risk": ("warn", "Financial risk level is high"),
    "email_unverified": ("warn", "Email not verified 24 hours after sign-up"),
    "setup_stuck": ("warn", "Setup not finished 3 days after sign-up"),
    "no_activity": ("info", "No transactions 7 days after sign-up"),
}
# Flags that only use the auth/support tables are filtered in the database; the others read
# the budgeting store (SQLite or Firestore) and are computed per user.
DB_FLAGS = ("deactivated", "email_failed", "open_ticket", "email_unverified", "setup_stuck")


# ---- Permissions ---------------------------------------------------------------

def is_staff(user) -> bool:
    return bool(user and user.is_authenticated and (user.is_staff or user.is_superuser))


class IsStaff(BasePermission):
    message = "Support staff only."

    def has_permission(self, request, view):
        return is_staff(request.user)


class IsSuperuser(BasePermission):
    message = "Only a superuser can change admin roles."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_superuser)


# ---- Audit log -------------------------------------------------------------------

def audit(actor, action: str, target_user=None, ticket=None, **detail) -> None:
    AdminAuditLog.objects.create(actor=actor, action=action, target_user=target_user, ticket=ticket, detail=detail)


def user_ref(user) -> Optional[dict]:
    if not user:
        return None
    return {"id": user.pk, "username": user.username, "email": user.email}


def audit_to_dict(row: AdminAuditLog) -> dict:
    return {
        "id": row.pk,
        "action": row.action,
        "actor": user_ref(row.actor),
        "target_user": user_ref(row.target_user),
        "ticket_id": row.ticket_id,
        "detail": row.detail or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ---- Issue flags -----------------------------------------------------------------

def annotate_users(qs):
    """Database-side facts used by the flags (one query for a whole page of users)."""
    week_ago = timezone.now() - EMAIL_FAILED_WINDOW
    return qs.annotate(
        _verified=Exists(UserProfile.objects.filter(user=OuterRef("pk"), email_verified=True)),
        _setup_done=Exists(UserProfile.objects.filter(user=OuterRef("pk"), setup_status=UserProfile.SETUP_COMPLETE)),
        _email_failed=Exists(EmailLog.objects.filter(user=OuterRef("pk"), status="failed", created_at__gte=week_ago)),
        _open_ticket=Exists(SupportTicket.objects.filter(user=OuterRef("pk"), status=SupportTicket.STATUS_OPEN)),
    )


def filter_by_db_flag(qs, flag: str):
    """qs must come from annotate_users()."""
    now = timezone.now()
    if flag == "deactivated":
        return qs.filter(is_active=False)
    if flag == "email_failed":
        return qs.filter(_email_failed=True)
    if flag == "open_ticket":
        return qs.filter(_open_ticket=True)
    if flag == "email_unverified":
        return qs.filter(_verified=False, date_joined__lte=now - UNVERIFIED_AFTER)
    if flag == "setup_stuck":
        return qs.filter(_setup_done=False, date_joined__lte=now - SETUP_STUCK_AFTER)
    return qs


def has_transactions(uid: str) -> bool:
    if settings.DATA_STORE == "sqlite":
        from budgeting.models import Transaction

        return Transaction.objects.filter(user_id=int(uid)).exists()
    from budgeting.store import TransactionFS

    return bool(TransactionFS.list_by_user(uid, limit=1))


def latest_risk(uid: str):
    from budgeting.store import RiskSnapshotFS

    rows = RiskSnapshotFS.list_since(uid, date.today() - timedelta(days=30))
    return rows[-1] if rows else None


def _fact(user, attr: str, query) -> bool:
    value = getattr(user, attr, None)
    return bool(query()) if value is None else bool(value)


def user_flags(user) -> List[dict]:
    """Issue flags for one user. Uses the annotate_users() values when present."""
    now = timezone.now()
    joined = user.date_joined or now
    verified = _fact(user, "_verified", lambda: UserProfile.objects.filter(user=user, email_verified=True).exists())
    setup_done = _fact(
        user, "_setup_done",
        lambda: UserProfile.objects.filter(user=user, setup_status=UserProfile.SETUP_COMPLETE).exists(),
    )
    email_failed = _fact(
        user, "_email_failed",
        lambda: EmailLog.objects.filter(user=user, status="failed", created_at__gte=now - EMAIL_FAILED_WINDOW).exists(),
    )
    open_ticket = _fact(
        user, "_open_ticket",
        lambda: SupportTicket.objects.filter(user=user, status=SupportTicket.STATUS_OPEN).exists(),
    )

    codes = []
    if not user.is_active:
        codes.append("deactivated")
    if email_failed:
        codes.append("email_failed")
    if open_ticket:
        codes.append("open_ticket")
    if not verified and now - joined >= UNVERIFIED_AFTER:
        codes.append("email_unverified")
    if not setup_done and now - joined >= SETUP_STUCK_AFTER:
        codes.append("setup_stuck")
    uid = str(user.pk)
    try:
        snap = latest_risk(uid)
        if snap and snap.level == "high":
            codes.append("high_risk")
        if now - joined >= NO_ACTIVITY_AFTER and not has_transactions(uid):
            codes.append("no_activity")
    except Exception as exc:  # the budgeting store being unavailable must not break support
        logger.warning("Could not compute store flags for user %s: %s", uid, exc)
    return [{"code": c, "severity": FLAGS[c][0], "text": FLAGS[c][1]} for c in codes]


def user_row(user) -> dict:
    """One line of the admin user list (user should come from annotate_users())."""
    return {
        "id": user.pk,
        "username": user.username,
        "email": user.email,
        "name": f"{user.first_name} {user.last_name}".strip(),
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "is_superuser": user.is_superuser,
        "email_verified": _fact(
            user, "_verified", lambda: UserProfile.objects.filter(user=user, email_verified=True).exists()
        ),
        "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "flags": user_flags(user),
    }


def search_users(q: str = "", status: str = ""):
    qs = annotate_users(User.objects.all()).order_by("-date_joined", "-pk")
    q = (q or "").strip()
    if q:
        qs = qs.filter(
            Q(username__icontains=q) | Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )
    if status == "active":
        qs = qs.filter(is_active=True)
    elif status == "inactive":
        qs = qs.filter(is_active=False)
    elif status == "staff":
        qs = qs.filter(Q(is_staff=True) | Q(is_superuser=True))
    return qs


def overview(for_user=None) -> dict:
    now = timezone.now()
    users = annotate_users(User.objects.all())
    tickets = SupportTicket.objects.all()
    return {
        "tickets_pool": tickets.filter(status=SupportTicket.STATUS_OPEN, assigned_to__isnull=True).count(),
        "tickets_resolved": tickets.filter(status=SupportTicket.STATUS_RESOLVED).count(),
        "my_open_tickets": tickets.filter(assigned_to=for_user).exclude(status=SupportTicket.STATUS_CLOSED).count()
        if for_user is not None
        else 0,
        "users_total": User.objects.count(),
        "users_new_7d": User.objects.filter(date_joined__gte=now - timedelta(days=7)).count(),
        "email_unverified": filter_by_db_flag(users, "email_unverified").count(),
        "setup_stuck": filter_by_db_flag(users, "setup_stuck").count(),
        "deactivated": User.objects.filter(is_active=False).count(),
        "tickets_open": SupportTicket.objects.filter(status=SupportTicket.STATUS_OPEN).count(),
        "tickets_waiting_user": SupportTicket.objects.filter(status=SupportTicket.STATUS_WAITING_USER).count(),
        "emails_failed_7d": EmailLog.objects.filter(status="failed", created_at__gte=now - EMAIL_FAILED_WINDOW).count(),
    }


# ---- Ticket settings ----------------------------------------------------------------

def get_support_settings():
    """The saved Support settings row, or an unsaved one built from the SUPPORT_* defaults."""
    from api.models import SupportSettings

    row = SupportSettings.objects.order_by("pk").first()
    if row:
        return row
    mode = getattr(settings, "SUPPORT_ASSIGNMENT_MODE", SupportSettings.MODE_LEAST_BUSY)
    if mode not in dict(SupportSettings.ASSIGNMENT_MODES):
        mode = SupportSettings.MODE_LEAST_BUSY
    return SupportSettings(
        assignment_mode=mode,
        reminder_days=int(getattr(settings, "SUPPORT_REMINDER_DAYS", 3)),
        auto_close_days=int(getattr(settings, "SUPPORT_AUTO_CLOSE_DAYS", 7)),
        email_admins=bool(getattr(settings, "SUPPORT_EMAIL_ADMINS", True)),
    )


def settings_to_dict(row) -> dict:
    from api.models import SupportSettings

    return {
        "assignment_mode": row.assignment_mode,
        "assignment_modes": [{"value": v, "label": label} for v, label in SupportSettings.ASSIGNMENT_MODES],
        "reminder_days": row.reminder_days,
        "auto_close_days": row.auto_close_days,
        "email_admins": row.email_admins,
        "saved": bool(row.pk),
        "updated_by": user_ref(row.updated_by) if row.pk else None,
        "updated_at": row.updated_at.isoformat() if row.pk and row.updated_at else None,
    }


# ---- Tickets ---------------------------------------------------------------------

def _staff_queryset(exclude=None):
    qs = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True), is_active=True)
    if exclude is not None:
        qs = qs.exclude(pk=exclude.pk)
    return qs


def pick_assignee(exclude=None, mode: Optional[str] = None):
    """
    The admin who should get the next ticket, or None (no admins, or pool mode).
      least_busy:  fewest tickets that are not closed; ties go to whoever was assigned least recently
      round_robin: whoever was assigned least recently (never assigned first)
    """
    from django.db.models import Count, Max

    mode = mode or get_support_settings().assignment_mode
    if mode == "pool":
        return None
    qs = _staff_queryset(exclude).annotate(
        _open=Count("assigned_tickets", filter=~Q(assigned_tickets__status=SupportTicket.STATUS_CLOSED)),
        _last=Max("assigned_tickets__assigned_at"),
    )
    candidates = list(qs)
    if not candidates:
        return None
    never = datetime(1900, 1, 1, tzinfo=dt_timezone.utc)

    def last(u):
        return u._last or never

    if mode == "round_robin":
        return min(candidates, key=lambda u: (last(u), u.pk))
    return min(candidates, key=lambda u: (u._open, last(u), u.pk))


def _notify(user_id, kind: str, title: str, body: str, link: str, ticket) -> None:
    from budgeting.store import NotificationFS

    try:
        NotificationFS(
            user_id=str(user_id), kind=kind, title=title[:200], body=(body or "")[:300], link=link,
            related_id=str(ticket.pk),
        ).save()
    except Exception as exc:
        logger.warning("Support notification %s failed for ticket %s: %s", kind, ticket.pk, exc)


def _email(send, **kwargs) -> None:
    try:
        send(**kwargs)
    except Exception as exc:
        logger.warning("Support email %s failed: %s", getattr(send, "__name__", send), exc)


def assign(ticket: SupportTicket, admin, by=None) -> SupportTicket:
    """Give the ticket to `admin` (None puts it back in the pool) and tell them."""
    from api.emails import send_ticket_assigned_email

    ticket.assigned_to = admin
    ticket.assigned_at = timezone.now() if admin else None
    ticket.save(update_fields=["assigned_to", "assigned_at", "updated_at"])
    audit(by, "ticket_assign", ticket.user, ticket, assigned_to=admin.pk if admin else None, automatic=by is None)
    if admin:
        _notify(admin.pk, "support_assigned", f"Ticket assigned to you: {ticket.subject}", ticket.subject,
                f"/admin/tickets/{ticket.pk}", ticket)
        if get_support_settings().email_admins:
            _email(send_ticket_assigned_email, admin=admin, ticket=ticket)
    return ticket


def auto_assign(ticket: SupportTicket, exclude=None) -> SupportTicket:
    """Assign by the configured mode; with no admin (or pool mode) the ticket stays in the pool."""
    admin = pick_assignee(exclude=exclude)
    if admin is None:
        if ticket.assigned_to_id:
            assign(ticket, None)
        return ticket
    return assign(ticket, admin)


def reassign_open_tickets_of(admin, by=None) -> int:
    """An admin left (deactivated / role removed): hand their unfinished tickets to others."""
    moved = 0
    for ticket in SupportTicket.objects.filter(assigned_to=admin).exclude(status=SupportTicket.STATUS_CLOSED):
        auto_assign(ticket, exclude=admin)
        moved += 1
    return moved


def assign_pool(limit: int = 200) -> int:
    """Hand out unassigned open tickets (used by the periodic job when admins become available)."""
    if get_support_settings().assignment_mode == "pool":
        return 0
    done = 0
    for ticket in SupportTicket.objects.filter(status=SupportTicket.STATUS_OPEN, assigned_to__isnull=True)[:limit]:
        admin = pick_assignee()
        if admin is None:
            break
        assign(ticket, admin)
        done += 1
    return done


def can_act(user, ticket: SupportTicket) -> bool:
    """Only the assigned admin (or a superuser) may answer, resolve or change a ticket."""
    return bool(user.is_superuser or (ticket.assigned_to_id and ticket.assigned_to_id == user.pk))


def ticket_to_dict(ticket: SupportTicket, *, messages: bool = False, for_staff: bool = False) -> dict:
    def iso(value):
        return value.isoformat() if value else None

    out = {
        "id": ticket.pk,
        "subject": ticket.subject,
        "category": ticket.category,
        "status": ticket.status,
        "priority": ticket.priority,
        "created_at": iso(ticket.created_at),
        "updated_at": iso(ticket.updated_at),
        "last_staff_reply_at": iso(ticket.last_staff_reply_at),
        "resolved_at": iso(ticket.resolved_at),
        "closed_at": iso(ticket.closed_at),
        "close_reason": ticket.close_reason,
    }
    if for_staff:
        out["user"] = user_ref(ticket.user)
        out["assigned_to"] = user_ref(ticket.assigned_to)
        out["assigned_at"] = iso(ticket.assigned_at)
    if messages:
        out["messages"] = [
            {
                "id": m.pk,
                "body": m.body,
                "from_staff": m.from_staff,
                "system": m.author_id is None,
                # Users see "Support" rather than which staff member answered.
                "author": (
                    "System" if m.author_id is None
                    else "Support" if m.from_staff and not for_staff
                    else m.author.username
                ),
                "created_at": iso(m.created_at),
            }
            for m in ticket.messages.select_related("author").all()
        ]
    return out


def _system_message(ticket: SupportTicket, body: str) -> None:
    SupportMessage.objects.create(ticket=ticket, author=None, body=body, from_staff=True)


def add_message(ticket: SupportTicket, author, body: str, *, from_staff: bool) -> SupportMessage:
    """A reply. Staff reply -> waiting_user; user reply -> open (back to the assigned admin)."""
    msg = SupportMessage.objects.create(ticket=ticket, author=author, body=body, from_staff=from_staff)
    if from_staff:
        ticket.status = SupportTicket.STATUS_WAITING_USER
        ticket.last_staff_reply_at = timezone.now()
    else:
        ticket.status = SupportTicket.STATUS_OPEN
        ticket.closed_at = None
        ticket.close_reason = ""
        ticket.resolved_at = None
        ticket.reminder_sent_at = None
    ticket.save()
    return msg


def notify_user_of_reply(ticket: SupportTicket, body: str) -> None:
    """In-app notification + email (an account email: sent even when notification emails are off)."""
    from api.emails import send_support_reply_email

    _notify(ticket.user_id, "support_reply", f"Support replied: {ticket.subject}", body,
            f"/support/{ticket.pk}", ticket)
    _email(send_support_reply_email, user=ticket.user, ticket_id=ticket.pk, subject=ticket.subject, reply=body)


def notify_assignee_of_user_reply(ticket: SupportTicket, body: str) -> None:
    """The user wrote again: tell the assigned admin (or every admin while it is in the pool)."""
    targets = [ticket.assigned_to] if ticket.assigned_to_id else list(_staff_queryset())
    for admin in targets:
        _notify(admin.pk, "support_ticket", f"User replied: {ticket.subject}", body,
                f"/admin/tickets/{ticket.pk}", ticket)


def notify_pool_ticket(ticket: SupportTicket, body: str) -> None:
    """A new ticket went to the pool: every admin can take it."""
    for admin in _staff_queryset():
        _notify(admin.pk, "support_ticket", f"New ticket in the pool: {ticket.subject}", body,
                f"/admin/tickets/{ticket.pk}", ticket)


def resolve(ticket: SupportTicket, admin, message: str) -> SupportTicket:
    """Support says it is fixed: the user is asked to confirm."""
    from api.emails import send_ticket_resolved_email

    SupportMessage.objects.create(ticket=ticket, author=admin, body=message, from_staff=True)
    now = timezone.now()
    ticket.status = SupportTicket.STATUS_RESOLVED
    ticket.resolved_at = now
    ticket.last_staff_reply_at = now
    ticket.reminder_sent_at = None
    ticket.save()
    _notify(ticket.user_id, "support_resolved", f"Is it fixed? {ticket.subject}", message,
            f"/support/{ticket.pk}", ticket)
    _email(send_ticket_resolved_email, user=ticket.user, ticket=ticket, message=message)
    audit(admin, "ticket_resolved", ticket.user, ticket)
    return ticket


def reopen(ticket: SupportTicket, user, comment: str = "") -> SupportTicket:
    """The user says it is not fixed: back to the same admin."""
    from api.emails import send_ticket_reopened_email

    text = comment.strip() or "Still not fixed."
    add_message(ticket, user, text, from_staff=False)
    if ticket.assigned_to_id:
        _notify(ticket.assigned_to_id, "support_reopened", f"Not fixed yet: {ticket.subject}", text,
                f"/admin/tickets/{ticket.pk}", ticket)
        if get_support_settings().email_admins:
            _email(send_ticket_reopened_email, admin=ticket.assigned_to, ticket=ticket, comment=comment.strip())
    else:
        auto_assign(ticket)
    audit(user, "ticket_reopened", ticket.user, ticket)
    return ticket


def close(ticket: SupportTicket, reason: str, by=None) -> SupportTicket:
    """Close and confirm by email to the user and the assigned admin."""
    from api.emails import send_ticket_closed_email

    ticket.status = SupportTicket.STATUS_CLOSED
    ticket.closed_at = timezone.now()
    ticket.close_reason = reason
    ticket.save()
    _system_message(
        ticket,
        "Closed: the user confirmed the problem is fixed." if reason == "user_confirmed"
        else "Closed automatically: no answer from the user.",
    )
    _notify(ticket.user_id, "support_closed", f"Closed: {ticket.subject}", "This request is closed.",
            f"/support/{ticket.pk}", ticket)
    _email(send_ticket_closed_email, recipient=ticket.user, ticket=ticket, for_admin=False)
    if ticket.assigned_to_id:
        _notify(ticket.assigned_to_id, "support_closed", f"Closed: {ticket.subject}",
                "The user confirmed the fix." if reason == "user_confirmed" else "Closed automatically.",
                f"/admin/tickets/{ticket.pk}", ticket)
        _email(send_ticket_closed_email, recipient=ticket.assigned_to, ticket=ticket, for_admin=True)
    audit(by, "ticket_closed", ticket.user, ticket, reason=reason)
    return ticket


def process_tickets(now=None) -> dict:
    """Periodic job: remind about resolved tickets, auto-close old ones, hand out the pool."""
    from api.emails import send_ticket_resolution_reminder_email

    now = now or timezone.now()
    cfg = get_support_settings()
    stats = {"reminded": 0, "closed": 0, "assigned": 0}
    resolved = SupportTicket.objects.filter(status=SupportTicket.STATUS_RESOLVED, resolved_at__isnull=False)
    if cfg.auto_close_days:
        for ticket in resolved.filter(resolved_at__lte=now - timedelta(days=cfg.auto_close_days)):
            close(ticket, "auto")
            stats["closed"] += 1
    if cfg.reminder_days:
        due = resolved.filter(resolved_at__lte=now - timedelta(days=cfg.reminder_days), reminder_sent_at__isnull=True)
        for ticket in due:
            left = 0
            if cfg.auto_close_days:
                left = max(0, cfg.auto_close_days - (now - ticket.resolved_at).days)
            _email(send_ticket_resolution_reminder_email, user=ticket.user, ticket=ticket, close_in_days=left)
            ticket.reminder_sent_at = now
            ticket.save(update_fields=["reminder_sent_at"])
            stats["reminded"] += 1
    stats["assigned"] = assign_pool()
    return stats
