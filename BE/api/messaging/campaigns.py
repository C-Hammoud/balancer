"""Campaigns: start (now or scheduled), send in resumable batches, and report stats."""
from __future__ import annotations

import logging
from typing import Optional

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.utils import timezone

from api import support
from api.messaging.audience import audience_users
from api.messaging.sending import compose, send_message
from api.models import Campaign, MessageDelivery

logger = logging.getLogger(__name__)
User = get_user_model()

BATCH_SIZE = 200
# A send started from the admin screen delivers this many right away; the scheduler does the rest.
INLINE_BATCH = 25


def campaign_stats(c: Campaign) -> dict:
    rows = c.deliveries.values("channel").annotate(
        total=Count("pk"),
        sent=Count("pk", filter=Q(status=MessageDelivery.SENT)),
        failed=Count("pk", filter=Q(status=MessageDelivery.FAILED)),
        skipped=Count("pk", filter=Q(status=MessageDelivery.SKIPPED)),
        read=Count("pk", filter=Q(read_at__isnull=False)),
        clicked=Count("pk", filter=Q(clicked_at__isnull=False)),
    )
    by_channel = {r["channel"]: {k: r[k] for k in ("total", "sent", "failed", "skipped", "read", "clicked")}
                  for r in rows}
    reached = c.deliveries.values("user_id").distinct().count()
    opted_out = c.deliveries.filter(detail__startswith="Opted out").values("user_id").distinct().count()
    return {
        "recipients": len(c.recipient_ids or []),
        "processed": reached,
        "opted_out": opted_out,
        "by_channel": by_channel,
    }


def campaign_to_dict(c: Campaign, *, stats: bool = True) -> dict:
    data = {
        "id": c.pk,
        "name": c.name,
        "category": c.category,
        "subject": c.subject,
        "body": c.body,
        "link": c.link,
        "link_label": c.link_label,
        "channels": list(c.channels or []),
        "audience": c.audience or {},
        "status": c.status,
        "scheduled_at": c.scheduled_at.isoformat() if c.scheduled_at else None,
        "started_at": c.started_at.isoformat() if c.started_at else None,
        "finished_at": c.finished_at.isoformat() if c.finished_at else None,
        "created_by": support.user_ref(c.created_by) if c.created_by_id else None,
        "sent_by": support.user_ref(c.sent_by) if c.sent_by_id else None,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }
    ids = (c.audience or {}).get("user_ids") or []
    if (c.audience or {}).get("type") == "users" and ids:
        # Names for the picked users (the audience only stores ids).
        data["audience_users"] = [support.user_ref(u) for u in User.objects.filter(pk__in=ids[:500]).order_by("username")]
    if stats:
        data["stats"] = campaign_stats(c)
    return data


def _start(c: Campaign) -> None:
    """Freeze the recipients and switch to sending."""
    c.recipient_ids = [u.pk for u in audience_users(c.audience or {})]
    c.status = Campaign.SENDING
    c.started_at = timezone.now()
    c.save(update_fields=["recipient_ids", "status", "started_at", "updated_at"])


def send_batch(c: Campaign, limit: int = BATCH_SIZE) -> int:
    """Send to up to `limit` recipients not reached yet; marks the campaign sent when done."""
    c.refresh_from_db()
    if c.status != Campaign.SENDING:
        return 0
    done = set(c.deliveries.values_list("user_id", flat=True))
    remaining = [i for i in (c.recipient_ids or []) if i not in done]
    users = list(User.objects.filter(pk__in=remaining).order_by("pk")[:limit]) if remaining else []
    for user in users:
        msg = compose(user, subject=c.subject, body=c.body, link=c.link, link_label=c.link_label,
                      category=c.category)
        send_message(user, msg, c.channels or [], template_key=f"campaign:{c.pk}"[:40],
                     sent_by=c.sent_by, campaign=c)
    # Recipients deleted since the start are never reached; finish when nobody else is left.
    if len(users) < limit:
        c.status = Campaign.SENT
        c.finished_at = timezone.now()
        c.save(update_fields=["status", "finished_at", "updated_at"])
    return len(users)


def process_campaigns(now=None, *, only: Optional[int] = None, max_per_run: int = 2000,
                      batch_size: int = BATCH_SIZE) -> dict:
    """Start due scheduled campaigns and continue the ones sending (the scheduler job)."""
    now = now or timezone.now()
    scope = Campaign.objects.all() if only is None else Campaign.objects.filter(pk=only)
    started = 0
    for c in scope.filter(status=Campaign.SCHEDULED, scheduled_at__lte=now):
        _start(c)
        started += 1
    sent = 0
    for c in scope.filter(status=Campaign.SENDING).order_by("pk"):
        # Batches until this campaign is done (send_batch marks it sent) or the run is full.
        while sent < max_per_run:
            sent += send_batch(c, min(batch_size, max_per_run - sent))
            if c.status != Campaign.SENDING:
                break
    return {"started": started, "messages": sent}
