from django.conf import settings
from django.db import models


class UserProfile(models.Model):
    SETUP_PENDING = "pending"
    SETUP_INCOMPLETE = "incomplete"
    SETUP_COMPLETE = "complete"
    SETUP_STATUS_CHOICES = (
        (SETUP_PENDING, "Pending"),
        (SETUP_INCOMPLETE, "Incomplete"),
        (SETUP_COMPLETE, "Complete"),
    )

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    email_verified = models.BooleanField(default=False)
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone = models.CharField(max_length=32, blank=True, default="")
    setup_status = models.CharField(
        max_length=20,
        choices=SETUP_STATUS_CHOICES,
        default=SETUP_PENDING,
    )
    setup_skipped_at = models.DateTimeField(null=True, blank=True)
    setup_completed_at = models.DateTimeField(null=True, blank=True)
    setup_nudge_push_due_at = models.DateTimeField(null=True, blank=True)
    setup_nudge_email_due_at = models.DateTimeField(null=True, blank=True)
    setup_nudge_push_sent_at = models.DateTimeField(null=True, blank=True)
    setup_nudge_email_sent_at = models.DateTimeField(null=True, blank=True)
    notify_weekly_summaries = models.BooleanField(default=True)
    notify_low_balance = models.BooleanField(default=True)
    notify_setup_nudges = models.BooleanField(default=True)
    notify_plan_updates = models.BooleanField(default=True)
    # Marketing messages from the admin notification center (opt-out: unsubscribe link / profile).
    notify_marketing = models.BooleanField(default=True)
    # Share of income the budget planner aims to save each month.
    savings_target_pct = models.PositiveSmallIntegerField(default=20)

    class Meta:
        verbose_name = "User profile"
        verbose_name_plural = "User profiles"

    def __str__(self) -> str:
        return f"Profile({self.user_id}, verified={self.email_verified}, setup={self.setup_status})"


# --- Customer support ----------------------------------------------------------


class SupportTicket(models.Model):
    """A problem a user reported from the app; staff answer it in the admin area."""

    CATEGORIES = (("account", "Account & sign-in"), ("bug", "Something is broken"), ("data", "My data"), ("other", "Other"))
    # open: support must act (unassigned = in the pool) · waiting_user: support asked the user something
    # resolved: support says it is fixed, waiting for the user to confirm · closed: done
    STATUS_OPEN = "open"
    STATUS_WAITING_USER = "waiting_user"
    STATUS_RESOLVED = "resolved"
    STATUS_CLOSED = "closed"
    STATUSES = (
        (STATUS_OPEN, "Open"),
        (STATUS_WAITING_USER, "Waiting for user"),
        (STATUS_RESOLVED, "Resolved, waiting for confirmation"),
        (STATUS_CLOSED, "Closed"),
    )
    PRIORITIES = (("normal", "Normal"), ("high", "High"))
    CLOSE_REASONS = (("", "—"), ("user_confirmed", "Confirmed fixed by the user"), ("auto", "Closed automatically"))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="support_tickets")
    subject = models.CharField(max_length=200)
    category = models.CharField(max_length=16, choices=CATEGORIES, default="other")
    status = models.CharField(max_length=16, choices=STATUSES, default=STATUS_OPEN, db_index=True)
    priority = models.CharField(max_length=8, choices=PRIORITIES, default="normal")
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_tickets"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_staff_reply_at = models.DateTimeField(null=True, blank=True)
    assigned_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    close_reason = models.CharField(max_length=20, choices=CLOSE_REASONS, blank=True, default="")

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["status", "assigned_to"], name="ticket_status_assignee")]

    def __str__(self) -> str:
        return f"#{self.pk} {self.subject} ({self.status})"


class SupportMessage(models.Model):
    ticket = models.ForeignKey(SupportTicket, on_delete=models.CASCADE, related_name="messages")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    body = models.TextField()
    from_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]


class EmailLog(models.Model):
    """Every email the app tried to send, so support can see what a user received."""

    KINDS = (("account", "Account"), ("notification", "Notification"))
    STATUSES = (("sent", "Sent"), ("failed", "Failed"), ("console", "Printed to console"))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    to = models.CharField(max_length=254, db_index=True)
    subject = models.CharField(max_length=255)
    kind = models.CharField(max_length=16, choices=KINDS, default="account")
    status = models.CharField(max_length=16, choices=STATUSES)
    error = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class AdminAuditLog(models.Model):
    """Who on the support team looked at or changed what."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+")
    action = models.CharField(max_length=40, db_index=True)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    ticket = models.ForeignKey(SupportTicket, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    detail = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class SupportSettings(models.Model):
    """
    How support tickets are handled; one row, edited by superusers in Admin -> Support settings.
    Defaults come from the environment (SUPPORT_* in .env) until a superuser saves the page.
    """

    MODE_LEAST_BUSY = "least_busy"
    MODE_ROUND_ROBIN = "round_robin"
    MODE_POOL = "pool"
    ASSIGNMENT_MODES = (
        (MODE_LEAST_BUSY, "Automatic: admin with the fewest open tickets"),
        (MODE_ROUND_ROBIN, "Automatic: each admin in turn"),
        (MODE_POOL, "Pool: admins take tickets themselves"),
    )

    assignment_mode = models.CharField(max_length=16, choices=ASSIGNMENT_MODES, default=MODE_LEAST_BUSY)
    # 0 turns the reminder / automatic close off.
    reminder_days = models.PositiveSmallIntegerField(default=3)
    auto_close_days = models.PositiveSmallIntegerField(default=7)
    email_admins = models.BooleanField(default=True, help_text="Email admins when a ticket is assigned or reopened")
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Support settings"
        verbose_name_plural = "Support settings"


# --- Messaging (admin notification center) ---------------------------------------


MESSAGE_CATEGORIES = (
    ("account", "Account notice"),
    ("reminder", "Reminder"),
    ("marketing", "Marketing"),
)
MESSAGE_CHANNELS = (("in_app", "In-app"), ("email", "Email"), ("sms", "SMS"))


class MessageTemplate(models.Model):
    """
    A reusable message (account notice, reminder or marketing) with {placeholders}.
    Built-in templates are created on first use and can be edited by superusers.
    """

    key = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    category = models.CharField(max_length=16, choices=MESSAGE_CATEGORIES, default="reminder")
    subject = models.CharField(max_length=200, blank=True, default="")
    body = models.TextField(blank=True, default="")
    # App route opened by the in-app notification / email button, e.g. /budgeting/transactions.
    link = models.CharField(max_length=300, blank=True, default="")
    link_label = models.CharField(max_length=60, blank=True, default="")
    channels = models.JSONField(default=list, blank=True)
    is_builtin = models.BooleanField(default=False)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "name"]

    def __str__(self) -> str:
        return f"{self.key} ({self.category})"


class Campaign(models.Model):
    """A message sent to an audience of users (marketing or reminder), now or at a set time."""

    DRAFT = "draft"
    SCHEDULED = "scheduled"
    SENDING = "sending"
    SENT = "sent"
    CANCELLED = "cancelled"
    STATUSES = (
        (DRAFT, "Draft"),
        (SCHEDULED, "Scheduled"),
        (SENDING, "Sending"),
        (SENT, "Sent"),
        (CANCELLED, "Cancelled"),
    )

    name = models.CharField(max_length=120)
    category = models.CharField(max_length=16, choices=MESSAGE_CATEGORIES, default="marketing")
    subject = models.CharField(max_length=200, blank=True, default="")
    body = models.TextField(blank=True, default="")
    link = models.CharField(max_length=300, blank=True, default="")
    link_label = models.CharField(max_length=60, blank=True, default="")
    channels = models.JSONField(default=list, blank=True)
    # {"type": "all" | "filter" | "users", "flags": [...], "countries": [...], ...}; see api.messaging.audience
    audience = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=STATUSES, default=DRAFT, db_index=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    # Recipients frozen when sending starts, so a resumed send reaches the same people.
    recipient_ids = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"#{self.pk} {self.name} ({self.status})"


class MessageDelivery(models.Model):
    """One message to one user on one channel: what was sent, how it went, read / clicked."""

    QUEUED = "queued"
    SENT = "sent"
    FAILED = "failed"
    SKIPPED = "skipped"
    STATUSES = ((QUEUED, "Queued"), (SENT, "Sent"), (FAILED, "Failed"), (SKIPPED, "Skipped"))

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="message_deliveries")
    campaign = models.ForeignKey(Campaign, null=True, blank=True, on_delete=models.CASCADE, related_name="deliveries")
    template_key = models.CharField(max_length=40, blank=True, default="")
    category = models.CharField(max_length=16, choices=MESSAGE_CATEGORIES, default="reminder")
    channel = models.CharField(max_length=16, choices=MESSAGE_CHANNELS)
    subject = models.CharField(max_length=200, blank=True, default="")
    # App route the message pointed to (opened after a tracked email click).
    link = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(max_length=16, choices=STATUSES, default=QUEUED, db_index=True)
    # Why it failed or was skipped (no email, opted out, account deactivated, ...).
    detail = models.CharField(max_length=300, blank=True, default="")
    # In-app: the notification id (read tracking).
    ref = models.CharField(max_length=64, blank=True, default="", db_index=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-pk"]
        indexes = [models.Index(fields=["campaign", "user"], name="delivery_campaign_user")]
