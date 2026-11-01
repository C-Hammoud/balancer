import logging
from datetime import timedelta

from django.utils import timezone

from api.models import UserProfile

logger = logging.getLogger(__name__)

SETUP_PUSH_COPY = "Finish setting up your wallet to start tracking your daily expenses!"


def get_user_profile(user) -> UserProfile:
    profile, _ = UserProfile.objects.get_or_create(user=user)
    return profile


def setup_payload(user) -> dict:
    profile = get_user_profile(user)
    return {
        "phone": profile.phone or "",
        "setup_status": profile.setup_status or UserProfile.SETUP_PENDING,
        "notify_weekly_summaries": bool(profile.notify_weekly_summaries),
        "notify_low_balance": bool(profile.notify_low_balance),
        "notify_setup_nudges": bool(profile.notify_setup_nudges),
        "notify_plan_updates": bool(profile.notify_plan_updates),
        "savings_target_pct": int(profile.savings_target_pct),
    }


def mark_setup_complete(user) -> UserProfile:
    profile = get_user_profile(user)
    profile.setup_status = UserProfile.SETUP_COMPLETE
    profile.setup_completed_at = timezone.now()
    profile.save(update_fields=["setup_status", "setup_completed_at"])
    return profile


def mark_setup_incomplete(user) -> UserProfile:
    profile = get_user_profile(user)
    now = timezone.now()
    profile.setup_status = UserProfile.SETUP_INCOMPLETE
    profile.setup_skipped_at = now
    fields = ["setup_status", "setup_skipped_at"]
    if profile.notify_setup_nudges:
        if not profile.setup_nudge_push_due_at:
            profile.setup_nudge_push_due_at = now + timedelta(hours=24)
            fields.append("setup_nudge_push_due_at")
        if not profile.setup_nudge_email_due_at:
            profile.setup_nudge_email_due_at = now + timedelta(hours=48)
            fields.append("setup_nudge_email_due_at")
    profile.save(update_fields=fields)
    return profile


def apply_profile_setup_patch(user, data: dict) -> UserProfile:
    profile = get_user_profile(user)
    fields = []
    if "phone" in data:
        profile.phone = str(data.get("phone") or "").strip()[:32]
        fields.append("phone")
    status = data.get("setup_status")
    if status == UserProfile.SETUP_COMPLETE:
        mark_setup_complete(user)
        profile = get_user_profile(user)
    elif status == UserProfile.SETUP_INCOMPLETE:
        mark_setup_incomplete(user)
        profile = get_user_profile(user)
    for field in ("notify_weekly_summaries", "notify_low_balance", "notify_setup_nudges", "notify_plan_updates"):
        if field in data:
            setattr(profile, field, bool(data.get(field)))
            fields.append(field)
    if "savings_target_pct" in data:
        try:
            pct = int(data.get("savings_target_pct"))
        except (TypeError, ValueError):
            pct = profile.savings_target_pct
        profile.savings_target_pct = max(0, min(pct, 90))
        fields.append("savings_target_pct")
    if fields:
        profile.save(update_fields=fields)
    return profile


def process_setup_nudges(limit: int = 25) -> dict:
    """Send due setup reminders (dev self-ping loop or `manage.py send_setup_nudges`)."""
    from api.emails import send_setup_nudge_email

    now = timezone.now()
    push_sent = 0
    email_sent = 0
    push_qs = UserProfile.objects.filter(
        setup_status=UserProfile.SETUP_INCOMPLETE,
        notify_setup_nudges=True,
        setup_nudge_push_due_at__lte=now,
        setup_nudge_push_sent_at__isnull=True,
    ).select_related("user")[:limit]
    for profile in push_qs:
        logger.info("Setup nudge (push) for user %s: %s", profile.user_id, SETUP_PUSH_COPY)
        profile.setup_nudge_push_sent_at = now
        profile.save(update_fields=["setup_nudge_push_sent_at"])
        push_sent += 1

    email_qs = UserProfile.objects.filter(
        setup_status=UserProfile.SETUP_INCOMPLETE,
        notify_setup_nudges=True,
        setup_nudge_email_due_at__lte=now,
        setup_nudge_email_sent_at__isnull=True,
    ).select_related("user")[:limit]
    for profile in email_qs:
        send_setup_nudge_email(profile.user)
        profile.setup_nudge_email_sent_at = now
        profile.save(update_fields=["setup_nudge_email_sent_at"])
        email_sent += 1
    return {"push_logged": push_sent, "emails_sent": email_sent}


def is_email_verified(user) -> bool:
    if not user or not user.pk:
        return False
    profile = UserProfile.objects.filter(user_id=user.pk).only("email_verified").first()
    return bool(profile and profile.email_verified)


def mark_email_verified(user) -> UserProfile:
    profile = get_user_profile(user)
    if not profile.email_verified:
        profile.email_verified = True
        profile.email_verified_at = timezone.now()
        profile.save(update_fields=["email_verified", "email_verified_at"])
    return profile


def mark_email_unverified(user) -> UserProfile:
    profile = get_user_profile(user)
    if profile.email_verified or profile.email_verified_at:
        profile.email_verified = False
        profile.email_verified_at = None
        profile.save(update_fields=["email_verified", "email_verified_at"])
    return profile
