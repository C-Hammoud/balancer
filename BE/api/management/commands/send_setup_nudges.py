"""
Send due onboarding (setup) reminder emails.

Schedule in production, e.g. every 30 minutes:
  python manage.py send_setup_nudges
"""
from django.core.management.base import BaseCommand

from api.user_profile import process_setup_nudges


class Command(BaseCommand):
    help = "Send due setup-reminder emails to users who have not finished onboarding"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100, help="Max users per run")

    def handle(self, *args, **options):
        stats = process_setup_nudges(limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(
                f"Setup nudges: {stats['emails_sent']} email(s), {stats['push_logged']} push logged."
            )
        )
