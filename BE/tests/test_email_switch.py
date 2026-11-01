"""NOTIFICATION_EMAILS_ENABLED=0 keeps account emails flowing and stops automatic notices."""
import pytest
from django.core import mail

from api.emails import send_budget_alert_email, send_risk_alert_email, send_verification_email

pytestmark = pytest.mark.django_db


def test_account_emails_still_sent_when_notifications_off(settings, user):
    settings.NOTIFICATION_EMAILS_ENABLED = False
    mail.outbox.clear()
    assert send_verification_email(user) is True
    assert len(mail.outbox) == 1
    assert user.email in mail.outbox[0].to


def test_notification_emails_not_sent_when_off(settings, user, capsys):
    settings.NOTIFICATION_EMAILS_ENABLED = False
    mail.outbox.clear()
    assert send_budget_alert_email(user=user, title="WARN: Food", description="95%", severity="WARN")
    assert send_risk_alert_email(user=user, title="High risk", description="Overdue", severity="CRITICAL")
    assert mail.outbox == []  # printed to the console instead
    assert "WARN: Food" in capsys.readouterr().out
