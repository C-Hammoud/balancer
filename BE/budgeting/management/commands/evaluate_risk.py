"""
Compute each user's debt & liquidity risk, save today's score for the history chart,
and raise / resolve risk alerts (emailed once when allowed).

Run manually or via cron / Task Scheduler (no frontend required):
  python manage.py evaluate_risk

Suggested schedule: once a day.
"""
from django.core.management.base import BaseCommand

from budgeting.alerts import _load_user, _users_for_alert_processing, evaluate_risk_alerts
from budgeting.risk import build_report


class Command(BaseCommand):
    help = "Compute risk scores, save daily snapshots and evaluate risk alerts"

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
            user = _load_user(uid)
            if not user:
                self.stderr.write(self.style.ERROR(f"User not found: {uid}"))
                return

        users, alerts, errors = 0, 0, 0
        for u in _users_for_alert_processing(user):
            users += 1
            try:
                report = build_report(u)
                alerts += len(evaluate_risk_alerts(u, report))
            except Exception as e:
                errors += 1
                self.stderr.write(f"User {getattr(u, 'pk', '?')}: {e}")
        self.stdout.write(
            self.style.SUCCESS(f"Processed {users} user(s); {alerts} open risk alert(s); {errors} error(s).")
        )
