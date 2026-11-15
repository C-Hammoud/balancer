"""Shared helpers for email verification links and token checks."""
import logging
from urllib.parse import quote, unquote, urlencode

from django.conf import settings
from django.contrib.auth import get_user_model
from api.tokens import email_verification_token
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from api.user_profile import activate_email, is_email_verified

User = get_user_model()
logger = logging.getLogger(__name__)


def decode_uid(uid_b64: str) -> str:
    """Decode url-safe base64 uid; restore padding stripped by some email clients."""
    value = (uid_b64 or "").strip()
    if not value:
        raise ValueError("empty uid")
    pad = (-len(value)) % 4
    if pad:
        value += "=" * pad
    return force_str(urlsafe_base64_decode(value))


def normalize_token(raw: str) -> str:
    return unquote((raw or "").strip())


def mobile_deep_link(path: str, **params) -> str:
    """Custom-scheme URL handled by Expo Router (financetracker://verify-email)."""
    scheme = getattr(settings, "MOBILE_APP_SCHEME", "financetracker")
    query = urlencode({k: str(v) for k, v in params.items() if v not in (None, "")})
    return f"{scheme}://{path.lstrip('/')}{'?' + query if query else ''}"


def web_verify_url(uid: str, token: str) -> str:
    """The web app's verify page; it confirms the token with a POST and shows the result."""
    base = settings.FRONTEND_URL.rstrip("/")
    return f"{base}/verify-email?uid={quote(uid, safe='')}&token={quote(token, safe='')}"


def build_email_verification_url(user) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    return web_verify_url(uid, email_verification_token.make_token(user))


def build_mobile_verify_url(user) -> str:
    uid = urlsafe_base64_encode(force_bytes(user.pk))
    token = email_verification_token.make_token(user)
    return mobile_deep_link("verify-email", uid=uid, token=token)


def build_password_reset_open_url(uid: str, token: str) -> str:
    base = settings.API_PUBLIC_URL.rstrip("/")
    return f"{base}/auth/password-reset/open/?uid={uid}&token={quote(token, safe='')}"


INVALID_LINK = "This link is invalid, expired or already used."
ACTIVATED = "Your account has been activated. You can sign in now."
ALREADY_ACTIVE = "Your account is already active. You can sign in."


def verify_email_with_token(uid_b64: str, raw_token: str) -> dict:
    """
    Returns {"ok": True, "detail": "...", "email_verified": True, "already_verified": bool}
    or {"ok": False, "detail": "..."}. The first activation also sends the "account is active" email.
    """
    token = normalize_token(raw_token)
    if not uid_b64 or not token:
        return {"ok": False, "detail": INVALID_LINK}

    try:
        uid = decode_uid(uid_b64)
        user = User.objects.get(pk=uid)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist) as exc:
        logger.info("Email verify failed: user lookup (%s)", exc)
        return {"ok": False, "detail": INVALID_LINK}

    if not email_verification_token.check_token(user, token):
        logger.info("Email verify failed: bad token for user %s", user.pk)
        return {"ok": False, "detail": INVALID_LINK}

    newly_activated = activate_email(user)
    if not is_email_verified(user):
        logger.error("Email verify save failed for user %s", user.pk)
        return {"ok": False, "detail": "Could not save verification status. Please try again."}
    if not newly_activated:
        return {"ok": True, "detail": ALREADY_ACTIVE, "email_verified": True, "already_verified": True}

    try:
        from budgeting.personal_budget_sharing_service import accept_pending_budget_invites

        accept_pending_budget_invites(user)
    except Exception as exc:
        logger.warning("Failed to apply pending budget invites for user %s: %s", user.pk, exc)

    try:
        from api.emails import send_account_activated_email

        send_account_activated_email(user)
    except Exception:
        # The account is active either way; a mail problem must not fail the verification.
        logger.warning("Account activated email failed for user %s", user.pk, exc_info=True)

    return {"ok": True, "detail": ACTIVATED, "email_verified": True, "already_verified": False}
