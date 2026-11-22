"""
Sections of the admin overview page (GET /admin/overview/?days=7|30|90).

Everything here reads the Django database (users, profiles, tickets, emails, audit log,
campaigns). The budgeting store, which can be Firestore, is only read for the recent sign-ups
of the activation funnel, and only when there are few enough of them.
"""
from __future__ import annotations

import logging
from datetime import datetime, time, timedelta
from statistics import median
from typing import Callable, Dict, List, Optional

from django.contrib.auth import get_user_model
from django.db.models import Count, Min, OuterRef, Q, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone

from api import support
from api.models import AdminAuditLog, Campaign, EmailLog, SupportMessage, SupportTicket, UserProfile

logger = logging.getLogger(__name__)
User = get_user_model()

PERIODS = (7, 30, 90)
# The funnel's "first transaction" step reads the budgeting store once per user: skip it for
# larger groups rather than slow the page down.
FUNNEL_STORE_LIMIT = 300
# A campaign still sending this long after it started means the scheduler is not running.
CAMPAIGN_STUCK_AFTER = timedelta(minutes=30)
# Opening a user page is recorded too, but it would fill the activity list.
ACTIVITY_SKIP = ("view_user",)


class Window:
    """The chosen period (ending today) and the one before it, on local calendar days."""

    def __init__(self, days: int, now=None):
        self.days = days
        self.now = now or timezone.now()
        today = timezone.localdate(self.now)
        self.first_day = today - timedelta(days=days - 1)
        self.start = timezone.make_aware(datetime.combine(self.first_day, time.min))
        self.prev_start = self.start - timedelta(days=days)

    def day_list(self) -> List:
        return [self.first_day + timedelta(days=i) for i in range(self.days)]

    def current(self, field: str) -> Q:
        return Q(**{f"{field}__gte": self.start})

    def previous(self, field: str) -> Q:
        return Q(**{f"{field}__gte": self.prev_start, f"{field}__lt": self.start})


def _daily(qs, field: str, w: Window) -> List[dict]:
    """[{"date", "count"}] for every day of the window (days without rows count 0)."""
    rows = (
        qs.filter(w.current(field))
        .annotate(_day=TruncDate(field))
        .values("_day")
        .annotate(n=Count("pk"))
    )
    by_day = {r["_day"]: r["n"] for r in rows}
    return [{"date": d.isoformat(), "count": by_day.get(d, 0)} for d in w.day_list()]


def _hours(delta: Optional[timedelta]) -> Optional[float]:
    return round(delta.total_seconds() / 3600, 1) if delta is not None else None


def _median_hours(deltas: List[timedelta]) -> Optional[float]:
    return _hours(median(deltas)) if deltas else None


# ---- Users -------------------------------------------------------------------------

def _first_transaction_count(user_ids: List[int]) -> Optional[int]:
    if len(user_ids) > FUNNEL_STORE_LIMIT:
        return None
    return sum(1 for uid in user_ids if support.has_transactions(str(uid)))


def users_section(w: Window) -> dict:
    users = User.objects.all()
    cohort = users.filter(w.current("date_joined"))
    cohort_ids = list(cohort.values_list("pk", flat=True))
    profiles = UserProfile.objects.filter(user_id__in=cohort_ids)
    try:
        with_transactions = _first_transaction_count(cohort_ids)
    except Exception as exc:  # the store being unavailable must not break the page
        logger.warning("Overview funnel: could not read transactions: %s", exc)
        with_transactions = None
    now = w.now
    return {
        "signups": {
            "series": _daily(users, "date_joined", w),
            "total": len(cohort_ids),
            "previous": users.filter(w.previous("date_joined")).count(),
        },
        "funnel": {
            "signed_up": len(cohort_ids),
            "verified": profiles.filter(email_verified=True).count(),
            "setup_complete": profiles.filter(setup_status=UserProfile.SETUP_COMPLETE).count(),
            # None: too many recent sign-ups to check, or the store could not be read.
            "first_transaction": with_transactions,
        },
        "active": {
            "day": users.filter(is_active=True, last_login__gte=now - timedelta(days=1)).count(),
            "week": users.filter(is_active=True, last_login__gte=now - timedelta(days=7)).count(),
            "month": users.filter(is_active=True, last_login__gte=now - timedelta(days=30)).count(),
            "never": users.filter(is_active=True, last_login__isnull=True).count(),
            "total": users.filter(is_active=True).count(),
        },
    }


# ---- Support ------------------------------------------------------------------------

def support_section(w: Window) -> dict:
    tickets = SupportTicket.objects.all()
    first_reply = (
        SupportMessage.objects.filter(ticket=OuterRef("pk"), from_staff=True, author__isnull=False)
        .order_by("created_at")
        .values("created_at")[:1]
    )
    replied = tickets.filter(w.current("created_at")).annotate(_first_reply=Subquery(first_reply))
    reply_times = [t._first_reply - t.created_at for t in replied if t._first_reply]
    resolve_times = [
        t.resolved_at - t.created_at
        for t in tickets.filter(w.current("resolved_at")).only("created_at", "resolved_at")
    ]
    oldest = tickets.filter(status=SupportTicket.STATUS_OPEN).select_related("assigned_to").order_by("updated_at").first()
    workload = (
        User.objects.filter(Q(is_staff=True) | Q(is_superuser=True), is_active=True)
        .annotate(
            _open=Count("assigned_tickets", filter=Q(assigned_tickets__status=SupportTicket.STATUS_OPEN)),
            _waiting=Count("assigned_tickets", filter=Q(
                assigned_tickets__status__in=(SupportTicket.STATUS_WAITING_USER, SupportTicket.STATUS_RESOLVED)
            )),
        )
        .order_by("-_open", "-_waiting", "username")
    )
    return {
        "opened": {
            "series": _daily(tickets, "created_at", w),
            "total": tickets.filter(w.current("created_at")).count(),
            "previous": tickets.filter(w.previous("created_at")).count(),
        },
        "closed": {
            "series": _daily(tickets, "closed_at", w),
            "total": tickets.filter(w.current("closed_at")).count(),
            "previous": tickets.filter(w.previous("closed_at")).count(),
        },
        "first_reply_hours": _median_hours(reply_times),
        "resolve_hours": _median_hours(resolve_times),
        "oldest_waiting": {
            "id": oldest.pk,
            "subject": oldest.subject,
            "since": oldest.updated_at.isoformat(),
            "hours": _hours(w.now - oldest.updated_at),
            "assigned_to": support.user_ref(oldest.assigned_to),
        } if oldest else None,
        "workload": [
            {"admin": support.user_ref(u), "open": u._open, "waiting": u._waiting} for u in workload
        ],
    }


# ---- Messaging ------------------------------------------------------------------------

def _campaign_row(c: Campaign) -> dict:
    from api.messaging.campaigns import campaign_stats

    return {
        "id": c.pk,
        "name": c.name,
        "status": c.status,
        "category": c.category,
        "scheduled_at": c.scheduled_at.isoformat() if c.scheduled_at else None,
        "started_at": c.started_at.isoformat() if c.started_at else None,
        "finished_at": c.finished_at.isoformat() if c.finished_at else None,
        "stats": campaign_stats(c),
    }


def messaging_section(w: Window) -> dict:
    campaigns = Campaign.objects.all()
    recent = campaigns.exclude(status=Campaign.DRAFT).order_by("-updated_at")[:5]
    upcoming = campaigns.filter(status=Campaign.SCHEDULED).order_by("scheduled_at").first()
    stuck = campaigns.filter(status=Campaign.SENDING, started_at__lt=w.now - CAMPAIGN_STUCK_AFTER).count()
    return {
        "recent": [_campaign_row(c) for c in recent],
        "next_scheduled": _campaign_row(upcoming) if upcoming else None,
        "stuck": stuck,
        "drafts": campaigns.filter(status=Campaign.DRAFT).count(),
    }


# ---- Email ---------------------------------------------------------------------------

def email_section(w: Window) -> dict:
    logs = EmailLog.objects.all()

    def counts(cond: Q) -> Dict[str, int]:
        rows = logs.filter(cond).values("status").annotate(n=Count("pk"))
        out = {"sent": 0, "failed": 0, "console": 0}
        out.update({r["status"]: r["n"] for r in rows if r["status"] in out})
        return out

    failures = logs.filter(status="failed").select_related("user").order_by("-created_at")[:5]
    return {
        "current": counts(w.current("created_at")),
        "previous": counts(w.previous("created_at")),
        "recent_failures": [
            {
                "id": f.pk,
                "to": f.to,
                "subject": f.subject,
                "error": (f.error or "")[:300],
                "user": support.user_ref(f.user),
                "created_at": f.created_at.isoformat() if f.created_at else None,
            }
            for f in failures
        ],
    }


# ---- Admin activity -------------------------------------------------------------------

def activity_section(w: Window) -> List[dict]:
    rows = (
        AdminAuditLog.objects.exclude(action__in=ACTIVITY_SKIP)
        .select_related("actor", "target_user")
        .order_by("-created_at")[:10]
    )
    return [support.audit_to_dict(r) for r in rows]


SECTIONS: Dict[str, Callable[[Window], object]] = {
    "users": users_section,
    "support": support_section,
    "messaging": messaging_section,
    "email": email_section,
    "activity": activity_section,
}


def dashboard(days: int, now=None) -> dict:
    """All sections; one that fails is None (and logged) so the others still show."""
    w = Window(days, now)
    out: dict = {"days": days, "generated_at": w.now.isoformat()}
    for name, build in SECTIONS.items():
        try:
            out[name] = build(w)
        except Exception:
            logger.exception("Admin overview section %s failed", name)
            out[name] = None
    return out
