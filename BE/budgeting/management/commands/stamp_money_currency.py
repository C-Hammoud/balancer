"""
Record the currency of budget lines, savings months and net-worth snapshots saved without one.

Older rows have no currency and were read as "the main currency", so after changing the main
currency they were relabelled instead of converted. This fills the blank currency only: amounts
are not changed and nothing is deleted, so it is safe to run more than once.

  python manage.py stamp_money_currency --currency SAR --dry-run
  python manage.py stamp_money_currency --currency SAR
  python manage.py stamp_money_currency --currency SAR --user 12
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from api.locale_defaults import VALID_CURRENCIES
from budgeting.currency_stamp import KINDS, stamp_blank_currency


class Command(BaseCommand):
    help = "Set the currency on budgets, savings and net-worth rows that have none"

    def add_arguments(self, parser):
        parser.add_argument("--currency", required=True, help="Currency the old amounts were entered in, e.g. SAR")
        parser.add_argument("--user", help="Only this user id (default: every user)")
        parser.add_argument("--dry-run", action="store_true", help="Count only, change nothing")

    def handle(self, *args, **options):
        code = (options["currency"] or "").strip().upper()
        if code not in VALID_CURRENCIES:
            raise CommandError(f"Unknown currency: {options['currency']}. Use one of {', '.join(sorted(VALID_CURRENCIES))}.")
        users = get_user_model().objects.all().order_by("pk")
        if options.get("user"):
            users = users.filter(pk=options["user"])
            if not users.exists():
                raise CommandError(f"No user with id {options['user']}.")
        dry = options["dry_run"]
        totals = {kind: 0 for kind, _ in KINDS}
        for user in users:
            counts = stamp_blank_currency(str(user.pk), code, dry_run=dry)
            if any(counts.values()):
                self.stdout.write(f"user {user.pk}: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
            for k, v in counts.items():
                totals[k] += v
        summary = ", ".join(f"{k} {v}" for k, v in totals.items())
        if dry:
            self.stdout.write(self.style.WARNING(f"Dry run, nothing changed. Would set {code} on: {summary}."))
        else:
            self.stdout.write(self.style.SUCCESS(f"Set {code} on: {summary}."))
