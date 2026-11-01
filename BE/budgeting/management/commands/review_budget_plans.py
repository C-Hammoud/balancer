"""
Suggest budget plans and notify users (in-app + email). Run daily, e.g. at 08:00:
  python manage.py review_budget_plans

Per user: new month without a plan, income that differs >10% from expected,
and (from day 15) spending that will miss the planned savings. Each notifies once per month.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from budgeting.plan_triggers import review_user


class Command(BaseCommand):
    help = "Suggest budget plans and send plan notifications"

    def add_arguments(self, parser):
        parser.add_argument("--username", default="", help="Only this user")

    def handle(self, *args, **options):
        users = get_user_model().objects.filter(is_active=True)
        if options["username"]:
            users = users.filter(username=options["username"])
        totals = {"users": 0, "monthly": 0, "income_change": 0, "overspending": 0, "errors": 0}
        for user in users.iterator():
            totals["users"] += 1
            try:
                for key, sent in review_user(user).items():
                    totals[key] += int(bool(sent))
            except Exception as exc:  # one user's bad data must not stop the run
                totals["errors"] += 1
                self.stderr.write(f"user {user.pk}: {exc}")
        self.stdout.write(self.style.SUCCESS(
            "Reviewed {users} user(s): {monthly} monthly, {income_change} income-change, "
            "{overspending} overspending notification(s); {errors} error(s).".format(**totals)
        ))
