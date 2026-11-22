"""Compose a message for a user and send it on the chosen channels, logging every delivery."""
from __future__ import annotations

import logging
from typing import Iterable, List, Optional

from api.messaging.channels import CHANNELS, Rendered
from api.messaging.missing import missing_items
from api.messaging.templates import build_context, render_text, uses_placeholder
from api.models import MessageDelivery
from api.user_profile import get_user_profile

logger = logging.getLogger(__name__)

OPTED_OUT = "Opted out of marketing messages."
DEACTIVATED = "The account is deactivated."


def compose(user, *, subject: str, body: str, link: str = "", link_label: str = "",
            category: str = "reminder", reason: str = "") -> Rendered:
    """The message with {placeholders} filled in for this user."""
    needs_missing = uses_placeholder(subject, "missing_items") or uses_placeholder(body, "missing_items")
    ctx = build_context(user, reason=reason, missing=missing_items(user) if needs_missing else None)
    return Rendered(
        subject=render_text(subject, ctx)[:200],
        body=render_text(body, ctx),
        link=(link or "").strip(),
        link_label=render_text(link_label, ctx)[:60],
        category=category,
    )


def skip_reason(user, category: str) -> str:
    """Why nothing at all may be sent to this user for this kind of message ('' when allowed)."""
    if category == "marketing" and not get_user_profile(user).notify_marketing:
        return OPTED_OUT
    # Account notices (e.g. "your account was deactivated") still reach deactivated users.
    if not user.is_active and category != "account":
        return DEACTIVATED
    return ""


def send_message(
    user,
    msg: Rendered,
    channels: Iterable[str],
    *,
    template_key: str = "",
    sent_by=None,
    campaign=None,
    force: bool = False,
) -> List[MessageDelivery]:
    """One delivery per channel: sent, failed, or skipped with the reason."""
    # force: a test send to the admin themself ignores their own opt-out.
    blocked = "" if force else skip_reason(user, msg.category)
    deliveries = []
    for code in dict.fromkeys(channels):
        channel = CHANNELS.get(code)
        if not channel:
            continue
        d = MessageDelivery(
            user=user, campaign=campaign, template_key=template_key[:40], category=msg.category,
            channel=code, subject=msg.subject[:200], link=msg.link[:300], sent_by=sent_by,
        )
        reason = blocked or channel.unavailable(user)
        if reason:
            d.status, d.detail = MessageDelivery.SKIPPED, reason[:300]
            d.save()
            deliveries.append(d)
            continue
        d.save()  # the id goes into tracked links
        try:
            channel.send(user, msg, d)
        except Exception as exc:
            logger.warning("Sending %s message to user %s failed: %s", code, user.pk, exc)
            d.status, d.detail = MessageDelivery.FAILED, str(exc)[:300]
        d.save()
        deliveries.append(d)
    return deliveries


def delivery_to_dict(d: MessageDelivery) -> dict:
    from api import support

    return {
        "id": d.pk,
        "user": support.user_ref(d.user) if d.user_id else None,
        "channel": d.channel,
        "status": d.status,
        "detail": d.detail,
        "subject": d.subject,
        "category": d.category,
        "template_key": d.template_key,
        "campaign_id": d.campaign_id,
        "campaign_name": d.campaign.name if d.campaign_id else "",
        "sent_by": support.user_ref(d.sent_by) if d.sent_by_id else None,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "read_at": d.read_at.isoformat() if d.read_at else None,
        "clicked_at": d.clicked_at.isoformat() if d.clicked_at else None,
    }


def mark_read(notification_ids: Iterable[str]) -> int:
    """In-app messages the user opened (called by the notification read endpoints)."""
    from django.utils import timezone

    ids = [str(i) for i in notification_ids if i]
    if not ids:
        return 0
    return MessageDelivery.objects.filter(channel="in_app", ref__in=ids, read_at__isnull=True).update(
        read_at=timezone.now()
    )


def channel_summary(deliveries: List[MessageDelivery]) -> Optional[str]:
    """One line for a toast: 'Email sent · In-app skipped (…)'."""
    if not deliveries:
        return None
    parts = []
    for d in deliveries:
        label = CHANNELS[d.channel].label if d.channel in CHANNELS else d.channel
        parts.append(f"{label} {d.status}" + (f" ({d.detail})" if d.detail and d.status != "sent" else ""))
    return " · ".join(parts)
