"""
Delivery channels. Each one says whether it can reach a user and sends one message.
A new channel (SMS provider, web push, ...) only needs a class here and an entry in CHANNELS.
"""
from __future__ import annotations

from dataclasses import dataclass

from api.models import MessageDelivery
from api.messaging.tokens import click_url, unsubscribe_url

FOOTER_REASON = {
    "account": "You are receiving this email because of a change to your Finance Tracker account.",
    "reminder": "You are receiving this reminder about your Finance Tracker account.",
    "marketing": "You are receiving this because marketing messages are turned on in your Finance Tracker profile.",
}


@dataclass
class Rendered:
    """A message with its placeholders filled in for one user."""

    subject: str
    body: str
    link: str = ""
    link_label: str = ""
    category: str = "reminder"


class Channel:
    code = ""
    label = ""
    enabled = True

    def unavailable(self, user) -> str:
        """Why this channel cannot reach the user ('' when it can)."""
        return "" if self.enabled else f"{self.label} is not set up yet."

    def send(self, user, msg: Rendered, delivery: MessageDelivery) -> None:
        """Send and set delivery.status / detail / ref (the caller saves the delivery)."""
        raise NotImplementedError


class InAppChannel(Channel):
    code = "in_app"
    label = "In-app"

    def unavailable(self, user) -> str:
        return "" if user.is_active else "The account is deactivated, so in-app messages cannot be seen."

    def send(self, user, msg: Rendered, delivery: MessageDelivery) -> None:
        from budgeting.store import NotificationFS

        n = NotificationFS(
            user_id=str(user.pk),
            kind="campaign" if delivery.campaign_id else "admin_message",
            title=msg.subject[:200],
            body=msg.body[:2000],
            link=msg.link,
            related_id=str(delivery.pk),
        )
        n.save()
        delivery.ref = str(n.pk or "")
        delivery.status = MessageDelivery.SENT


class EmailChannel(Channel):
    code = "email"
    label = "Email"

    def unavailable(self, user) -> str:
        return "" if (user.email or "").strip() else "The user has no email address."

    def send(self, user, msg: Rendered, delivery: MessageDelivery) -> None:
        from api.email_delivery import send_branded_email
        from api.email_template import BrandedEmail, EmailCTA

        paragraphs = [p.strip() for p in msg.body.split("\n\n") if p.strip()]
        headers = None
        secondary = None
        if msg.category == "marketing":
            url = unsubscribe_url(user.pk)
            secondary = EmailCTA(label="Unsubscribe from marketing emails", url=url)
            headers = {"List-Unsubscribe": f"<{url}>"}
        content = BrandedEmail(
            subject=msg.subject,
            preheader=" ".join(msg.body.split())[:120],
            headline=msg.subject,
            paragraphs=paragraphs,
            cta=EmailCTA(label=msg.link_label or "Open Finance Tracker", url=click_url(delivery.pk))
            if msg.link else None,
            secondary_cta=secondary,
            footer_reason=FOOTER_REASON.get(msg.category, ""),
        )
        if send_branded_email(content, [user.email], notification=True, headers=headers):
            delivery.status = MessageDelivery.SENT
        else:
            delivery.status = MessageDelivery.FAILED
            delivery.detail = "The email could not be sent; see the email log."


class SmsChannel(Channel):
    """Placeholder until an SMS provider and phone verification are added."""

    code = "sms"
    label = "SMS"
    enabled = False


CHANNELS = {c.code: c for c in (InAppChannel(), EmailChannel(), SmsChannel())}


def channel_list() -> list:
    return [{"code": c.code, "label": c.label, "enabled": c.enabled} for c in CHANNELS.values()]
