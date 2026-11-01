"""
Evaluate budget utilization + commitment due alerts and email new ones.

Run manually or via cron / Task Scheduler (no frontend required):
  python manage.py process_budget_alerts

Suggested schedule: every 15–60 minutes, or daily after bank imports.
"""
from django.core.management.base import BaseCommand

from budgeting.alerts import process_budget_alerts


class Command(BaseCommand):
    help = "Evaluate budget alerts and send email for new open alerts"

    def add_arguments(self, parser):
        parser.add_argument(
            "--user-id",
            type=str,
            default="",
            help="Process a single user id (default: all users with budgeting data)",
        )

    def handle(self, *args, **options):
        user = None
        uid = (options.get("user_id") or "").strip()
        if uid:
            from budgeting.alerts import _load_user

            user = _load_user(uid)
            if not user:
                self.stderr.write(self.style.ERROR(f"User not found: {uid}"))
                return

        stats = process_budget_alerts(user=user)
        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {stats['users']} user(s); "
                f"sent {stats['emails_sent']} alert email(s); "
                f"{stats['errors']} error(s)."
            )
        )
