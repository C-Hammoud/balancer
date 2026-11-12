"""
Run every background job on its own interval, forever (the `scheduler` container in production).

  python manage.py run_scheduler            # loop
  python manage.py run_scheduler --once     # run every job once and exit (smoke test)

Intervals (minutes) can be overridden with SCHEDULE_<JOB>_MINUTES, e.g. SCHEDULE_BUDGET_ALERTS_MINUTES=15.
A failing job is logged and retried on its next turn; it never stops the other jobs.
The nightly backup runs `pg_dump` into BACKUP_DIR when DATABASE_URL points to PostgreSQL.
BACKUP_ENABLED=0 turns it off where the host backs up the database and the disk is temporary (Render).
"""
from __future__ import annotations

import gzip
import logging
import os
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import close_old_connections

logger = logging.getLogger("scheduler")

# name -> (default interval in minutes, how to run it)
JOBS = {
    "budget_alerts": (30, lambda: call_command("process_budget_alerts")),
    "setup_nudges": (30, lambda: call_command("send_setup_nudges")),
    "support_tickets": (60, lambda: call_command("process_support_tickets")),
    "risk": (24 * 60, lambda: call_command("evaluate_risk")),
    "commitment_reminders": (24 * 60, lambda: call_command("send_commitment_reminders")),
    "budget_plans": (24 * 60, lambda: call_command("review_budget_plans")),
    "backup": (24 * 60, lambda: backup_database()),
}


def interval_minutes(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(f"SCHEDULE_{name.upper()}_MINUTES", default)))
    except ValueError:
        return default


def backup_database() -> str:
    """pg_dump the PostgreSQL database into BACKUP_DIR (gzipped) and keep the newest BACKUP_KEEP files."""
    if os.environ.get("BACKUP_ENABLED", "1") == "0":
        return "skipped (BACKUP_ENABLED=0)"
    url = os.environ.get("DATABASE_URL", "")
    if not url.startswith(("postgres://", "postgresql://")):
        return "skipped (not PostgreSQL)"
    folder = Path(os.environ.get("BACKUP_DIR", "/backups"))
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"balancer-{datetime.now():%Y%m%d-%H%M%S}.sql.gz"
    dump = subprocess.run(["pg_dump", "--no-owner", "--dbname", url], capture_output=True, check=True)
    with gzip.open(target, "wb") as fh:
        fh.write(dump.stdout)
    keep = int(os.environ.get("BACKUP_KEEP", "14"))
    for old in sorted(folder.glob("balancer-*.sql.gz"))[:-keep]:
        old.unlink(missing_ok=True)
    return str(target)


class Command(BaseCommand):
    help = "Run the background jobs (alerts, reminders, risk, support tickets, backups) on intervals"

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run every job once, then exit")

    def handle(self, *args, once: bool = False, **options):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s scheduler %(levelname)s %(message)s")
        if once:
            for name in JOBS:
                self.run_job(name)
            return
        if not shutil.which("pg_dump") and os.environ.get("DATABASE_URL", "").startswith("postgres"):
            logger.warning("pg_dump not found: database backups will fail")
        # Start staggered by a minute so the API finishes its migrations first.
        due = {name: datetime.now() + timedelta(minutes=1) for name in JOBS}
        logger.info("started; jobs: %s", ", ".join(f"{n}={interval_minutes(n, d)}m" for n, (d, _) in JOBS.items()))
        while True:
            now = datetime.now()
            for name, (default, _) in JOBS.items():
                if now >= due[name]:
                    self.run_job(name)
                    due[name] = datetime.now() + timedelta(minutes=interval_minutes(name, default))
            time.sleep(20)

    def run_job(self, name: str) -> None:
        close_old_connections()  # long-running process: never reuse a dropped DB connection
        started = time.monotonic()
        try:
            result = JOBS[name][1]()
            logger.info("%s ok in %.1fs%s", name, time.monotonic() - started, f" ({result})" if result else "")
        except Exception:
            logger.exception("%s failed", name)
        finally:
            close_old_connections()
