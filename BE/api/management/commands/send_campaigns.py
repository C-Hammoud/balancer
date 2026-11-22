"""
Start due scheduled campaigns and send the next batches of the ones in progress.

Run by the scheduler (job "campaigns"), or by hand:
  python manage.py send_campaigns
"""
from django.core.management.base import BaseCommand

from api.messaging.campaigns import process_campaigns


class Command(BaseCommand):
    help = "Send due admin notification campaigns in batches"

    def add_arguments(self, parser):
        parser.add_argument("--max", type=int, default=2000, help="Max messages per run")

    def handle(self, *args, **options):
        stats = process_campaigns(max_per_run=options["max"])
        self.stdout.write(self.style.SUCCESS(
            f"Campaigns: {stats['started']} started, {stats['messages']} recipient(s) processed."
        ))
