"""Send multipart (HTML + plain) branded transactional email."""
from __future__ import annotations

import logging
from typing import Sequence

from django.conf import settings
from django.core.mail import EmailMultiAlternatives, get_connection

from api.email_template import BrandedEmail, render_html, render_plain_text

logger = logging.getLogger(__name__)


def from_email() -> str:
    return getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@financetracker.local")


def send_branded_email(content: BrandedEmail, to: Sequence[str], *, notification: bool = False) -> bool:
    """
    notification=True marks automatic notices (budget/risk alerts, payment reminders, plan
    suggestions, setup nudges). With NOTIFICATION_EMAILS_ENABLED=0 they are printed to the
    console instead of sent, while account emails (verification, password reset, invites) still go out.
    """
    recipients = [e.strip() for e in to if (e or "").strip()]
    if not recipients:
        return False
    connection = None
    if notification and not getattr(settings, "NOTIFICATION_EMAILS_ENABLED", True):
        connection = get_connection("django.core.mail.backends.console.EmailBackend")

    plain = render_plain_text(content)
    html = render_html(content)
    msg = EmailMultiAlternatives(
        subject=content.subject,
        body=plain,
        from_email=from_email(),
        to=recipients,
        connection=connection,
    )
    msg.attach_alternative(html, "text/html")
    kind = "notification" if notification else "account"
    try:
        msg.send(fail_silently=False)
    except Exception as exc:
        logger.warning("Failed to send email %r to %s: %s", content.subject, recipients, exc)
        _log(recipients, content.subject, kind, "failed", str(exc))
        return False
    backend = connection or msg.get_connection()
    to_console = "console" in type(backend).__module__
    _log(recipients, content.subject, kind, "console" if to_console else "sent")
    return True


def _log(recipients: Sequence[str], subject: str, kind: str, status: str, error: str = "") -> None:
    """Record the attempt for the support screens. Never lets logging break sending."""
    try:
        from django.contrib.auth import get_user_model

        from api.models import EmailLog

        User = get_user_model()
        for to in recipients:
            user = User.objects.filter(email__iexact=to).order_by("pk").first()
            EmailLog.objects.create(
                user=user, to=to[:254], subject=(subject or "")[:255], kind=kind, status=status, error=error[:2000]
            )
    except Exception as exc:  # e.g. table missing before migrate
        logger.debug("Could not record email log: %s", exc)
