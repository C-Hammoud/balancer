"""The production job runner: every job runs once without errors; a failing job does not stop the others."""
import logging

import pytest
from django.core.management import call_command

from api.management.commands import run_scheduler

pytestmark = pytest.mark.django_db


def test_every_job_runs_once(caplog, make_user):
    make_user()
    with caplog.at_level(logging.INFO, logger="scheduler"):
        call_command("run_scheduler", "--once")
    messages = [r.getMessage() for r in caplog.records if r.name == "scheduler"]
    for name in run_scheduler.JOBS:
        assert any(m.startswith(f"{name} ok") for m in messages), (name, messages)
    # SQLite in tests: the PostgreSQL backup is skipped, not failed.
    assert any("backup ok" in m and "skipped" in m for m in messages)


def test_a_failing_job_does_not_stop_the_rest(caplog, monkeypatch):
    def boom():
        raise RuntimeError("SMTP down")

    jobs = dict(run_scheduler.JOBS)
    jobs["budget_alerts"] = (30, boom)
    monkeypatch.setattr(run_scheduler, "JOBS", jobs)
    with caplog.at_level(logging.INFO, logger="scheduler"):
        call_command("run_scheduler", "--once")
    messages = [r.getMessage() for r in caplog.records if r.name == "scheduler"]
    assert "budget_alerts failed" in messages
    assert any(m.startswith("risk ok") for m in messages)


def test_backup_can_be_switched_off(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@db/x")
    monkeypatch.setenv("BACKUP_ENABLED", "0")
    assert run_scheduler.backup_database() == "skipped (BACKUP_ENABLED=0)"


def test_interval_override(monkeypatch):
    monkeypatch.setenv("SCHEDULE_BUDGET_ALERTS_MINUTES", "5")
    assert run_scheduler.interval_minutes("budget_alerts", 30) == 5
    monkeypatch.setenv("SCHEDULE_BUDGET_ALERTS_MINUTES", "soon")
    assert run_scheduler.interval_minutes("budget_alerts", 30) == 30
