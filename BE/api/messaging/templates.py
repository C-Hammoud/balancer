"""Message templates: the built-in set, {placeholder} rendering and the per-user context."""
from __future__ import annotations

import re
from typing import Dict, List, Optional

from django.conf import settings

from api.models import MessageTemplate

# Placeholders an admin can use in a subject or body; shown in the editor.
PLACEHOLDERS = [
    {"key": "first_name", "description": "First name (the username when no first name is set)"},
    {"key": "last_name", "description": "Last name"},
    {"key": "username", "description": "Username"},
    {"key": "email", "description": "Email address"},
    {"key": "app_link", "description": "Address of the app"},
    {"key": "support_email", "description": "Support email address"},
    {"key": "missing_items", "description": "What the user has not filled in yet, one item per line"},
    {"key": "reason", "description": "The reason entered when (de)activating the account"},
]

BUILTIN_TEMPLATES: List[dict] = [
    {
        "key": "account_deactivated",
        "name": "Account deactivated",
        "category": "account",
        "channels": ["email"],
        "subject": "Your Finance Tracker account was deactivated",
        "body": (
            "Hi {first_name},\n\n"
            "Your Finance Tracker account has been deactivated, so you can no longer sign in.\n"
            "{reason}\n\n"
            "If you think this is a mistake, contact us at {support_email}."
        ),
        "link": "",
        "link_label": "",
    },
    {
        "key": "account_reactivated",
        "name": "Account reactivated",
        "category": "account",
        "channels": ["email", "in_app"],
        "subject": "Your Finance Tracker account is active again",
        "body": (
            "Hi {first_name},\n\n"
            "Good news: your account has been reactivated and you can sign in again.\n"
            "{reason}"
        ),
        "link": "/dashboard",
        "link_label": "Sign in",
    },
    {
        "key": "complete_setup",
        "name": "Complete your setup",
        "category": "reminder",
        "channels": ["in_app", "email"],
        "subject": "Finish setting up Finance Tracker",
        "body": (
            "Hi {first_name},\n\n"
            "You are a few steps away from seeing where your money goes. Add your accounts and your "
            "monthly income to finish setting up."
        ),
        "link": "/dashboard",
        "link_label": "Finish setup",
    },
    {
        "key": "verify_email",
        "name": "Verify your email",
        "category": "reminder",
        "channels": ["email"],
        "subject": "Please verify your email address",
        "body": (
            "Hi {first_name},\n\n"
            "Your email address is not verified yet. Verify it from your profile so we can reach you "
            "about your account."
        ),
        "link": "/profile",
        "link_label": "Open my profile",
    },
    {
        "key": "add_transactions",
        "name": "Add your recent transactions",
        "category": "reminder",
        "channels": ["in_app", "email"],
        "subject": "Keep your spending up to date",
        "body": (
            "Hi {first_name},\n\n"
            "You have not added transactions for a while. Add or import your recent spending to keep "
            "your budget and reports accurate."
        ),
        "link": "/budgeting/transactions",
        "link_label": "Add transactions",
    },
    {
        "key": "missing_data",
        "name": "Missing data reminder",
        "category": "reminder",
        "channels": ["in_app", "email"],
        "subject": "A few things are missing in your Finance Tracker",
        "body": (
            "Hi {first_name},\n\n"
            "To get the most out of Finance Tracker, please complete these:\n"
            "{missing_items}"
        ),
        "link": "/dashboard",
        "link_label": "Open Finance Tracker",
    },
    {
        "key": "announcement",
        "name": "Announcement / new feature",
        "category": "marketing",
        "channels": ["in_app", "email"],
        "subject": "Something new in Finance Tracker",
        "body": "Hi {first_name},\n\nWe have just added something we think you will like.",
        "link": "/dashboard",
        "link_label": "Take a look",
    },
    {
        "key": "custom",
        "name": "Custom message",
        "category": "reminder",
        "channels": ["in_app"],
        "subject": "",
        "body": "Hi {first_name},\n\n",
        "link": "",
        "link_label": "",
    },
]

_PLACEHOLDER_RE = re.compile(r"\{([a-z_]+)\}")


def ensure_builtin_templates() -> None:
    """Create any built-in template that is missing (edited ones are left as they are)."""
    existing = set(MessageTemplate.objects.values_list("key", flat=True))
    for spec in BUILTIN_TEMPLATES:
        if spec["key"] not in existing:
            MessageTemplate.objects.create(is_builtin=True, **spec)


def get_template(key: str) -> Optional[MessageTemplate]:
    ensure_builtin_templates()
    return MessageTemplate.objects.filter(key=key).first()


def template_to_dict(t: MessageTemplate) -> dict:
    return {
        "key": t.key,
        "name": t.name,
        "category": t.category,
        "subject": t.subject,
        "body": t.body,
        "link": t.link,
        "link_label": t.link_label,
        "channels": list(t.channels or []),
        "is_builtin": t.is_builtin,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


def uses_placeholder(text: str, key: str) -> bool:
    return "{" + key + "}" in (text or "")


def render_text(text: str, context: Dict[str, str]) -> str:
    """Fill {placeholders} from context; unknown ones are left as typed."""
    rendered = _PLACEHOLDER_RE.sub(lambda m: context.get(m.group(1), m.group(0)), text or "")
    # A placeholder that rendered empty on its own line leaves no blank gap.
    return re.sub(r"\n{3,}", "\n\n", rendered).strip()


def build_context(user, *, reason: str = "", missing: Optional[List[dict]] = None) -> Dict[str, str]:
    reason = (reason or "").strip()
    ctx = {
        "first_name": (user.first_name or user.username or "there").strip(),
        "last_name": (user.last_name or "").strip(),
        "username": user.username or "",
        "email": user.email or "",
        "app_link": getattr(settings, "FRONTEND_URL", "http://localhost:4200").rstrip("/"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", "") or getattr(settings, "DEFAULT_FROM_EMAIL", ""),
        "reason": f"Reason: {reason}" if reason else "",
    }
    if missing is not None:
        ctx["missing_items"] = (
            "\n".join(f"• {m['text']}" for m in missing) if missing else "• Nothing — you are all set."
        )
    return ctx
