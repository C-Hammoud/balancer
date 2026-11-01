"""Transactional emails using the branded template."""
from __future__ import annotations

import logging
from urllib.parse import quote

from django.contrib.auth.tokens import default_token_generator
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from api.email_delivery import send_branded_email
from api.email_template import BrandedEmail, EmailCTA
from api.email_verification import build_email_verification_url, build_mobile_verify_url

logger = logging.getLogger(__name__)


def _display_name(user, fallback: str = "there") -> str:
    return (getattr(user, "first_name", None) or getattr(user, "username", None) or fallback).strip()


def _sharer_display(user) -> str:
    parts = [getattr(user, "first_name", ""), getattr(user, "last_name", "")]
    return " ".join(filter(None, parts)).strip() or getattr(user, "username", "Someone")


def send_welcome_and_verification_email(user) -> bool:
    email = (user.email or "").strip()
    if not email:
        logger.info("Welcome/verification email skipped: user %s has no email.", user.pk)
        return False

    verify_url = build_email_verification_url(user)
    name = _display_name(user)
    content = BrandedEmail(
        subject="Welcome to Finance Tracker — verify your email",
        preheader="Confirm your email to start tracking budgets and expenses.",
        headline=f"Welcome, {name}!",
        paragraphs=[
            "Your Finance Tracker account is ready. Verify your email address to sign in and "
            "start planning budgets, tracking transactions, and reaching your financial goals.",
            "This verification link expires after a while. If it stops working, request a new "
            "one from the sign-in page.",
        ],
        cta=EmailCTA(label="Verify email address", url=verify_url),
        secondary_cta=EmailCTA(label="Already have the app? Open Finance Tracker", url=build_mobile_verify_url(user)),
        secondary_note="If you did not create this account, you can safely ignore this email.",
        footer_reason="You received this email because an account was registered with this address.",
    )
    return send_branded_email(content, [email])


def send_verification_email(user) -> bool:
    email = (user.email or "").strip()
    if not email:
        return False

    verify_url = build_email_verification_url(user)
    name = _display_name(user)
    content = BrandedEmail(
        subject="Verify your Finance Tracker email",
        preheader="Confirm your email to continue using Finance Tracker.",
        headline="Verify your email",
        paragraphs=[
            f"Hello {name},",
            "Use the button below to verify your email address.",
        ],
        cta=EmailCTA(label="Verify email address", url=verify_url),
        secondary_cta=EmailCTA(label="Already have the app? Open Finance Tracker", url=build_mobile_verify_url(user)),
        secondary_note="If you did not request this, you can ignore this email.",
        footer_reason="You received this because a verification was requested for your account.",
    )
    return send_branded_email(content, [email])


def send_setup_nudge_email(user) -> bool:
    email = (getattr(user, "email", None) or "").strip()
    if not email:
        return False
    from django.conf import settings

    name = _display_name(user)
    frontend = getattr(settings, "FRONTEND_URL", "http://localhost:4200").rstrip("/")
    content = BrandedEmail(
        subject="Complete your profile to get a clear view of your monthly spending.",
        preheader="Add a main account so income and expenses can be balanced.",
        headline="Finish setting up your wallet",
        paragraphs=[
            f"Hello {name},",
            "You skipped adding a main account. Without one, income and expenses can't be balanced.",
            "Add a bank, cash, or card account to start tracking daily spending.",
        ],
        cta=EmailCTA(label="Complete your profile", url=f"{frontend}/login"),
        secondary_note="You can also open Profile in the mobile app and tap the setup banner.",
        footer_reason="You received this because you skipped wallet setup. Turn off setup nudges in Profile to stop these emails.",
    )
    return send_branded_email(content, [email], notification=True)


def send_password_reset_email(user, reset_url: str, app_url: str = "") -> bool:
    email = (user.email or "").strip()
    if not email:
        logger.info("Password reset skipped: user %s has no email.", user.pk)
        return False

    name = _display_name(user)
    content = BrandedEmail(
        subject="Reset your Finance Tracker password",
        preheader="Use this link to choose a new password. Link expires soon.",
        headline="Reset your password",
        paragraphs=[
            f"Hello {name},",
            "We received a request to reset your Finance Tracker password. "
            "Click the button below to choose a new one.",
        ],
        cta=EmailCTA(label="Reset password", url=reset_url),
        secondary_cta=EmailCTA(label="Open in the Finance Tracker app", url=app_url) if app_url else None,
        secondary_note="This link is valid for a limited time. If you did not request a reset, ignore this email.",
        footer_reason="You received this because a password reset was requested for your account.",
    )
    return send_branded_email(content, [email])


def send_support_reply_email(*, user, ticket_id, subject: str, reply: str) -> bool:
    """Support answered a ticket. An account email: sent even when notification emails are off."""
    email = (getattr(user, "email", None) or "").strip()
    if not email:
        return False

    from django.conf import settings

    frontend = getattr(settings, "FRONTEND_URL", "http://localhost:4200").rstrip("/")
    content = BrandedEmail(
        subject=f"Support replied: {subject}",
        preheader=reply[:120],
        headline="Support replied to your request",
        paragraphs=[f"Hello {_display_name(user)},", reply],
        detail_rows=[("Request", f"#{ticket_id} {subject}")],
        cta=EmailCTA(label="View the conversation", url=f"{frontend}/support/{ticket_id}"),
        footer_reason="You received this because you contacted Finance Tracker support.",
    )
    return send_branded_email(content, [email])


# Support ticket workflow. All are account emails: sent even when notification emails are off.

def _frontend() -> str:
    from django.conf import settings

    return getattr(settings, "FRONTEND_URL", "http://localhost:4200").rstrip("/")


def _ticket_row(ticket) -> tuple:
    return ("Request", f"#{ticket.pk} {ticket.subject}")


def send_ticket_assigned_email(*, admin, ticket) -> bool:
    email = (getattr(admin, "email", None) or "").strip()
    if not email:
        return False
    content = BrandedEmail(
        subject=f"New support ticket for you: #{ticket.pk} {ticket.subject}",
        preheader="A support ticket was assigned to you.",
        headline="A support ticket was assigned to you",
        paragraphs=[f"Hello {_display_name(admin)},", f"{ticket.user.username} needs help with: {ticket.subject}"],
        detail_rows=[_ticket_row(ticket), ("Category", ticket.get_category_display()), ("Priority", ticket.priority)],
        cta=EmailCTA(label="Open the ticket", url=f"{_frontend()}/admin/tickets/{ticket.pk}"),
        footer_reason="You received this because you are on the Finance Tracker support team.",
    )
    return send_branded_email(content, [email])


def send_ticket_resolved_email(*, user, ticket, message: str) -> bool:
    email = (getattr(user, "email", None) or "").strip()
    if not email:
        return False
    url = f"{_frontend()}/support/{ticket.pk}"
    content = BrandedEmail(
        subject=f"Is it fixed? #{ticket.pk} {ticket.subject}",
        preheader="Support thinks your problem is fixed. Please confirm.",
        headline="We think your problem is fixed",
        paragraphs=[f"Hello {_display_name(user)},", message, "Please let us know if it works for you now."],
        detail_rows=[_ticket_row(ticket)],
        cta=EmailCTA(label="Yes, it's fixed", url=f"{url}?confirm=yes"),
        secondary_cta=EmailCTA(label="Still not fixed", url=f"{url}?confirm=no"),
        footer_reason="You received this because you contacted Finance Tracker support.",
    )
    return send_branded_email(content, [email])


def send_ticket_resolution_reminder_email(*, user, ticket, close_in_days: int) -> bool:
    email = (getattr(user, "email", None) or "").strip()
    if not email:
        return False
    url = f"{_frontend()}/support/{ticket.pk}"
    closing = f"If we don't hear from you, the request closes automatically in {close_in_days} day(s)." if close_in_days else ""
    content = BrandedEmail(
        subject=f"Reminder: is it fixed? #{ticket.pk} {ticket.subject}",
        preheader="Please confirm whether your problem is fixed.",
        headline="Is your problem fixed?",
        paragraphs=[p for p in (f"Hello {_display_name(user)},", "Support marked your request as fixed. Please confirm.", closing) if p],
        detail_rows=[_ticket_row(ticket)],
        cta=EmailCTA(label="Yes, it's fixed", url=f"{url}?confirm=yes"),
        secondary_cta=EmailCTA(label="Still not fixed", url=f"{url}?confirm=no"),
        footer_reason="You received this because you contacted Finance Tracker support.",
    )
    return send_branded_email(content, [email])


def send_ticket_reopened_email(*, admin, ticket, comment: str) -> bool:
    email = (getattr(admin, "email", None) or "").strip()
    if not email:
        return False
    content = BrandedEmail(
        subject=f"Not fixed yet: #{ticket.pk} {ticket.subject}",
        preheader="The user says the problem is not fixed.",
        headline="The user says it is not fixed yet",
        paragraphs=[f"Hello {_display_name(admin)},", comment or "The user did not add a comment."],
        detail_rows=[_ticket_row(ticket), ("User", ticket.user.username)],
        cta=EmailCTA(label="Open the ticket", url=f"{_frontend()}/admin/tickets/{ticket.pk}"),
        footer_reason="You received this because this support ticket is assigned to you.",
    )
    return send_branded_email(content, [email])


def send_ticket_closed_email(*, recipient, ticket, for_admin: bool) -> bool:
    """Confirmation that a ticket is closed, worded for the user or the assigned admin."""
    email = (getattr(recipient, "email", None) or "").strip()
    if not email:
        return False
    auto = ticket.close_reason == "auto"
    if for_admin:
        why = (
            "It was closed automatically because the user did not answer."
            if auto
            else f"{ticket.user.username} confirmed that the problem is fixed."
        )
        url = f"{_frontend()}/admin/tickets/{ticket.pk}"
        reason = "You received this because this support ticket was assigned to you."
    else:
        why = (
            "We closed it because we did not hear back from you. Reply to it any time to reopen it."
            if auto
            else "Thank you for confirming that the problem is fixed."
        )
        url = f"{_frontend()}/support/{ticket.pk}"
        reason = "You received this because you contacted Finance Tracker support."
    content = BrandedEmail(
        subject=f"Closed: #{ticket.pk} {ticket.subject}",
        preheader="This support request is now closed.",
        headline="Support request closed",
        paragraphs=[f"Hello {_display_name(recipient)},", why],
        detail_rows=[_ticket_row(ticket)],
        cta=EmailCTA(label="View the request", url=url),
        footer_reason=reason,
    )
    return send_branded_email(content, [email])


def send_budget_shared_email(*, recipient, shared_by, budget_name: str, budget_id: str, role: str) -> bool:
    email = (getattr(recipient, "email", None) or "").strip()
    if not email:
        logger.info("Budget share email skipped: recipient %s has no email.", getattr(recipient, "pk", "?"))
        return False

    sharer_name = _sharer_display(shared_by)
    recipient_name = _display_name(recipient)
    perm_label = "Viewer" if role == "viewer" else "Editor"
    from django.conf import settings

    frontend = getattr(settings, "FRONTEND_URL", "http://localhost:4200").rstrip("/")
    budget_url = f"{frontend}/budgeting/budgets/{budget_id}"

    content = BrandedEmail(
        subject=f'{sharer_name} shared "{budget_name}" with you',
        preheader=f"You have {perm_label.lower()} access to this budget on Finance Tracker.",
        headline="A budget was shared with you",
        paragraphs=[f"Hello {recipient_name},"],
        detail_rows=[
            ("Shared by", sharer_name),
            ("Budget", budget_name),
            ("Your access", perm_label),
        ],
        cta=EmailCTA(label="View budget", url=budget_url),
        secondary_note="After signing in, you can also find this budget under Budgets → Shared with me.",
        footer_reason=f"You received this because {sharer_name} shared a budget with your account.",
    )
    return send_branded_email(content, [email])


def send_budget_invite_email(
    *,
    recipient_email: str,
    shared_by,
    budget_name: str,
    budget_id: str,
    role: str,
) -> bool:
    email = (recipient_email or "").strip()
    if not email:
        return False

    sharer_name = _sharer_display(shared_by)
    perm_label = "Viewer" if role == "viewer" else "Editor"
    from django.conf import settings

    frontend = getattr(settings, "FRONTEND_URL", "http://localhost:4200").rstrip("/")
    register_url = f"{frontend}/register?email={quote(email)}"

    content = BrandedEmail(
        subject=f'{sharer_name} invited you to "{budget_name}"',
        preheader="Create a free Finance Tracker account to accept this budget invitation.",
        headline="You're invited to collaborate",
        paragraphs=[
            f"{sharer_name} wants to share a personal budget with you on Finance Tracker — "
            "plan and track spending for trips, projects, and goals in one place.",
            "Create an account with this email address to accept the invitation.",
        ],
        detail_rows=[
            ("Budget", budget_name),
            ("Access level", perm_label),
            ("Invited by", sharer_name),
        ],
        cta=EmailCTA(label="Create account & accept", url=register_url),
        secondary_note=(
            "After you register and verify your email, the budget will appear under "
            "Budgets → Shared with me."
        ),
        footer_reason=f"You received this because {sharer_name} invited you to a shared budget.",
    )
    return send_branded_email(content, [email])


def send_budget_alert_email(*, user, title: str, description: str, severity: str) -> bool:
    email = (getattr(user, "email", None) or "").strip()
    if not email:
        return False

    from django.conf import settings

    frontend = getattr(settings, "FRONTEND_URL", "http://localhost:4200").rstrip("/")
    alerts_url = f"{frontend}/budgeting/alerts"

    content = BrandedEmail(
        subject=f"Budget alert: {title}",
        preheader=description[:120] if description else "Review this alert in Finance Tracker.",
        headline=title,
        paragraphs=[description] if description else [],
        detail_rows=[("Severity", severity.title())] if severity else [],
        cta=EmailCTA(label="Review alerts", url=alerts_url),
        footer_reason="You received this because a budget threshold or alert was triggered on your account.",
    )
    return send_branded_email(content, [email], notification=True)


def send_risk_alert_email(*, user, title: str, description: str, severity: str) -> bool:
    email = (getattr(user, "email", None) or "").strip()
    if not email:
        return False

    from django.conf import settings

    frontend = getattr(settings, "FRONTEND_URL", "http://localhost:4200").rstrip("/")
    risk_url = f"{frontend}/budgeting/risk"

    content = BrandedEmail(
        subject=f"Risk alert: {title}",
        preheader=description[:120] if description else "Review your financial risk in Finance Tracker.",
        headline=title,
        paragraphs=[description] if description else [],
        detail_rows=[("Level", "High" if severity == "CRITICAL" else "Elevated")],
        cta=EmailCTA(label="Review your risk", url=risk_url),
        footer_reason=(
            "You received this because risk alerts and low-balance notifications are enabled. "
            "You can turn them off in Risk settings or your profile."
        ),
    )
    return send_branded_email(content, [email], notification=True)


def send_commitment_reminder_email(
    *,
    user,
    commitment_name: str,
    due_date: str,
    amount: str,
    sequence: int,
) -> bool:
    email = (getattr(user, "email", None) or "").strip()
    if not email:
        return False

    from django.conf import settings

    frontend = getattr(settings, "FRONTEND_URL", "http://localhost:4200").rstrip("/")
    commitments_url = f"{frontend}/budgeting/commitments"

    content = BrandedEmail(
        subject=f"Payment reminder: {commitment_name}",
        preheader=f"Installment #{sequence} is due soon.",
        headline="Upcoming commitment payment",
        paragraphs=[
            f'A payment for "{commitment_name}" is due soon.',
        ],
        detail_rows=[
            ("Due date", due_date),
            ("Amount", str(amount)),
            ("Installment", f"#{sequence}"),
        ],
        cta=EmailCTA(label="View commitments", url=commitments_url),
        footer_reason="You received this because payment reminders are enabled for this commitment.",
    )
    return send_branded_email(content, [email], notification=True)


def send_plan_suggestion_email(*, user, plan: dict, headline: str, intro: str, link_path: str) -> bool:
    """Suggested budget plan: summary table and a button to review/accept it in the app."""
    email = (getattr(user, "email", None) or "").strip()
    if not email:
        return False

    from django.conf import settings

    frontend = getattr(settings, "FRONTEND_URL", "http://localhost:4200").rstrip("/")
    cur = plan.get("currency", "")

    def fmt(value) -> str:
        return f"{float(value):,.0f} {cur}".strip()

    rows = [
        ("Expected income", fmt(plan["income_total"])),
        ("Commitments due", fmt(plan["commitments_total"])),
        ("Needs", fmt(plan["needs_total"])),
        ("Wants", fmt(plan["wants_total"])),
        ("Savings", f"{fmt(plan['savings_amount'])} ({plan.get('savings_pct', 0)}%)"),
    ]
    paragraphs = [intro] + [f"Note: {w}" for w in (plan.get("warnings") or [])[:3]]
    content = BrandedEmail(
        subject=f"{headline} ({plan['year']}-{int(plan['month']):02d})",
        preheader=intro[:120],
        headline=headline,
        paragraphs=paragraphs,
        detail_rows=rows,
        cta=EmailCTA(label="Review the plan", url=f"{frontend}{link_path}"),
        footer_reason="You received this because budget plan updates are on. Turn them off in your profile.",
    )
    return send_branded_email(content, [email], notification=True)
