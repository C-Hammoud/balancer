"""
Send email reminders for upcoming commitment installment due dates.

Run manually or via cron:
  python manage.py send_commitment_reminders
"""
from django.core.management.base import BaseCommand

from budgeting.commitment_schedule import evaluate_commitment_reminders


class Command(BaseCommand):
    help = "Email commitment payment reminders within each commitment's configured window"

    def handle(self, *args, **options):
        sent = evaluate_commitment_reminders(user=None)
        self.stdout.write(self.style.SUCCESS(f"Sent {sent} commitment reminder email(s)."))
