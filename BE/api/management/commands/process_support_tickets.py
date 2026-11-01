"""
Support ticket housekeeping (run hourly via cron / Task Scheduler):
  - remind users about tickets support marked as fixed (after Support settings -> reminder days)
  - close tickets the user never confirmed (after auto-close days) and email user + admin
  - hand out tickets waiting in the pool when an admin is available

  python manage.py process_support_tickets
"""
from django.core.management.base import BaseCommand

from api.support import process_tickets


class Command(BaseCommand):
    help = "Send fix-confirmation reminders, auto-close unconfirmed tickets and assign pool tickets"

    def handle(self, *args, **options):
        stats = process_tickets()
        self.stdout.write(
            self.style.SUCCESS(
                f"Reminded {stats['reminded']}, closed {stats['closed']}, assigned {stats['assigned']} ticket(s)."
            )
        )
