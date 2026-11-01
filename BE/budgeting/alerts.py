"""
Budget utilization alerts + commitment due-date alerts.
"""
import logging
import time
from decimal import Decimal
from datetime import date, timedelta
from threading import Lock

from django.conf import settings
from django.utils import timezone

from .alert_state import RESOLUTION_AUTO, RESOLUTION_USER, alert_is_snoozed
from .commitment_schedule import ensure_schedule
from .store import BudgetAlertFS, CommitmentFS
from .services import UNMAPPED_CATEGORY_ID, budget_utilization_report, _user_id

logger = logging.getLogger(__name__)

# In-process throttle: avoid re-running heavy Firestore eval on every GET /alerts/.
_ALERT_EVAL_CACHE: dict[str, float] = {}
_ALERT_EVAL_LOCK = Lock()
BUDGET_ALERT_TTL_SECONDS = int(getattr(settings, "BUDGET_ALERT_TTL_SECONDS", 300))
COMMITMENT_ALERT_TTL_SECONDS = int(getattr(settings, "COMMITMENT_ALERT_TTL_SECONDS", 300))
RISK_ALERT_TTL_SECONDS = int(getattr(settings, "RISK_ALERT_TTL_SECONDS", 900))


def invalidate_alert_eval_cache(user) -> None:
    uid = _user_id(user)
    with _ALERT_EVAL_LOCK:
        for key in list(_ALERT_EVAL_CACHE):
            if key.startswith(f"{uid}:"):
                del _ALERT_EVAL_CACHE[key]


def refresh_alerts_for_user(user, year=None, month=None, *, force: bool = False) -> None:
    """Re-evaluate utilization + commitment due alerts (throttled unless force=True)."""
    today = date.today()
    year = int(year if year is not None else today.year)
    month = int(month if month is not None else today.month)
    uid = _user_id(user)
    budget_key = f"{uid}:budget:{year}:{month}"
    commitment_key = f"{uid}:commitment"
    risk_key = f"{uid}:risk"
    now = time.monotonic()

    run_budget = force
    run_commitment = force
    run_risk = force
    with _ALERT_EVAL_LOCK:
        if not run_budget:
            last = _ALERT_EVAL_CACHE.get(budget_key, 0.0)
            run_budget = now - last >= BUDGET_ALERT_TTL_SECONDS
        if not run_commitment:
            last = _ALERT_EVAL_CACHE.get(commitment_key, 0.0)
            run_commitment = now - last >= COMMITMENT_ALERT_TTL_SECONDS
        if not run_risk:
            last = _ALERT_EVAL_CACHE.get(risk_key, 0.0)
            run_risk = now - last >= RISK_ALERT_TTL_SECONDS

    if run_budget:
        evaluate_budget_alerts(user, year, month)
        with _ALERT_EVAL_LOCK:
            _ALERT_EVAL_CACHE[budget_key] = time.monotonic()
    if run_commitment:
        evaluate_commitment_due_alerts(user)
        with _ALERT_EVAL_LOCK:
            _ALERT_EVAL_CACHE[commitment_key] = time.monotonic()
    if run_risk:
        # Risk reads every part of the user's data; a failure must not break the other alerts.
        try:
            evaluate_risk_alerts(user)
        except Exception as e:
            logger.warning("evaluate_risk_alerts failed for user %s: %s", uid, e)
        with _ALERT_EVAL_LOCK:
            _ALERT_EVAL_CACHE[risk_key] = time.monotonic()


def _save_alert_if_changed(alert, **fields) -> bool:
    """Apply fields; save only when something changed. Returns True if saved."""
    changed = False
    for key, value in fields.items():
        if getattr(alert, key) != value:
            setattr(alert, key, value)
            changed = True
    if changed:
        alert.save()
    return changed


def _open_state_fields(alert) -> dict:
    """
    Fields that keep an alert open while its condition holds.
    Alerts the user resolved stay resolved; auto-resolved ones reopen.
    """
    if alert.is_resolved and (getattr(alert, "resolution", "") or "") == RESOLUTION_USER:
        return {}
    return {"is_resolved": False, "resolution": "", "resolved_at": None}


def _auto_resolve(alert) -> None:
    alert.is_resolved = True
    alert.resolution = RESOLUTION_AUTO
    alert.resolved_at = timezone.now()
    alert.save()


def _should_email(alert) -> bool:
    return not alert.email_sent and not alert.is_resolved and not alert_is_snoozed(alert)

def evaluate_budget_alerts(user, year=None, month=None):
    """
    Compare utilization report to thresholds; create/update open alerts; resolve alerts
    that fall back under threshold; email once per fingerprint when enabled.
    Commitment payments are excluded from utilization (due-date alerts only).
    Returns list of currently open utilization alerts for the month.
    """
    today = date.today()
    year = int(year if year is not None else today.year)
    month = int(month if month is not None else today.month)
    uid = _user_id(user)

    try:
        report = budget_utilization_report(user, year, month)
    except Exception as e:
        logger.warning("budget_utilization_report failed: %s", e)
        return []

    desired = {}  # fingerprint -> row meta for WARN/CRITICAL
    for row in report["rows"]:
        cat_id = row["category_id"]
        # Never raise utilization alerts for synthetic commitment categories
        if str(cat_id or "").startswith("commitment:"):
            continue
        util = row.get("utilization_pct")
        status = row.get("status") or "ok"
        if status not in ("warn", "critical", "over"):
            continue
        if status == "warn":
            severity = "WARN"
        else:
            severity = "CRITICAL"
        severities = [severity]
        if severity == "CRITICAL" and util is not None and util >= row.get("warn_pct", Decimal("80")):
            severities = ["WARN", "CRITICAL"]
        for sev in severities:
            fp = BudgetAlertFS.make_fingerprint(uid, year, month, cat_id, sev)
            desired[fp] = {
                "category_id": cat_id,
                "severity": sev,
                "utilization_pct": util,
                "actual": row["actual"],
                "forecast": row["forecast"],
                "category_name": row.get("category_name") or cat_id,
                "email_enabled": row.get("email_enabled", True),
            }

    open_alerts = []
    all_user_alerts = BudgetAlertFS.list_by_user(uid, open_only=False, limit=500)
    existing_month = [
        a for a in all_user_alerts
        if a.year == year and a.month == month and _is_utilization_alert(a)
    ]
    by_fp = {a.fingerprint: a for a in existing_month if a.fingerprint}

    for fp, meta in desired.items():
        if meta["category_id"] == UNMAPPED_CATEGORY_ID:
            title = f"{meta['severity']}: Unmapped expenses"
            description = (
                f"You have {meta['actual']} in expenses without a category mapping "
                f"for {year}-{month:02d}. Open type maps to assign expense types to budget categories."
            )
        else:
            title = f"{meta['severity']}: {meta['category_name']} budget"
            util_str = f"{meta['utilization_pct']}%" if meta["utilization_pct"] is not None else "n/a"
            description = (
                f"{meta['category_name']} utilization is {util_str} "
                f"(actual {meta['actual']}, forecast {meta['forecast']}) for {year}-{month:02d}."
            )
        alert = by_fp.get(fp)
        if alert:
            _save_alert_if_changed(
                alert,
                title=title,
                description=description,
                alert_type="utilization",
                utilization_pct=meta["utilization_pct"],
                actual=meta["actual"],
                forecast=meta["forecast"],
                **_open_state_fields(alert),
            )
        else:
            alert = BudgetAlertFS(
                user_id=uid,
                year=year,
                month=month,
                category_id=meta["category_id"],
                severity=meta["severity"],
                title=title,
                description=description,
                alert_type="utilization",
                utilization_pct=meta["utilization_pct"],
                actual=meta["actual"],
                forecast=meta["forecast"],
                is_resolved=False,
                email_sent=False,
                fingerprint=fp,
            )
            alert.save()
            by_fp[fp] = alert

        if meta.get("email_enabled", True) and _should_email(alert):
            if _send_alert_email(user, alert):
                alert.email_sent = True
                alert.save()

        if not alert.is_resolved:
            open_alerts.append(alert)

    for alert in existing_month:
        if alert.fingerprint and alert.fingerprint not in desired and not alert.is_resolved:
            _auto_resolve(alert)

    return open_alerts


def evaluate_commitment_due_alerts(user) -> list:
    """
    In-app due-date alerts for commitment installments (upcoming within reminder window, or overdue).
    No utilization metrics — commitments are not budget-utilization alerts.
    """
    uid = _user_id(user)
    today = date.today()
    desired = {}
    open_alerts = []

    for c in CommitmentFS.list_by_user(uid):
        days_before = int(getattr(c, "reminder_days_before", None) or 3)
        lines = ensure_schedule(c)
        for line in lines:
            if line.status != "outstanding" or not line.due_date:
                continue
            due = line.due_date
            overdue = due < today
            window_start = due - timedelta(days=days_before)
            upcoming = window_start <= today <= due
            if not overdue and not upcoming:
                continue
            severity = "CRITICAL" if overdue else "WARN"
            fp = f"{uid}|due|{line.pk}|{severity}"
            due_str = due.isoformat()
            amt = line.amount
            if overdue:
                title = f"Overdue: {c.name}"
                description = (
                    f"Commitment “{c.name}” payment of {amt} was due on {due_str} "
                    f"and is still outstanding."
                )
            else:
                title = f"Due soon: {c.name}"
                description = (
                    f"Commitment “{c.name}” payment of {amt} is due on {due_str}."
                )
            desired[fp] = {
                "year": due.year,
                "month": due.month,
                "category_id": f"commitment:{c.pk}",
                "severity": severity,
                "title": title,
                "description": description,
                "actual": amt,
                "forecast": Decimal("0"),
                "commitment_id": c.pk,
                "schedule_line_id": line.pk,
                "due_date": due_str,
                "commitment_name": c.name,
            }

    all_user_alerts = BudgetAlertFS.list_by_user(uid, open_only=False, limit=500)
    existing_due = [a for a in all_user_alerts if _is_commitment_due_alert(a)]
    by_fp = {a.fingerprint: a for a in existing_due if a.fingerprint}

    for fp, meta in desired.items():
        alert = by_fp.get(fp)
        if alert:
            _save_alert_if_changed(
                alert,
                title=meta["title"],
                description=meta["description"],
                severity=meta["severity"],
                year=meta["year"],
                month=meta["month"],
                category_id=meta["category_id"],
                alert_type="commitment_due",
                utilization_pct=None,
                actual=meta["actual"],
                forecast=meta["forecast"],
                commitment_id=meta.get("commitment_id") or "",
                schedule_line_id=meta.get("schedule_line_id") or "",
                due_date=meta.get("due_date") or "",
                commitment_name=meta.get("commitment_name") or "",
                **_open_state_fields(alert),
            )
        else:
            alert = BudgetAlertFS(
                user_id=uid,
                year=meta["year"],
                month=meta["month"],
                category_id=meta["category_id"],
                severity=meta["severity"],
                title=meta["title"],
                description=meta["description"],
                alert_type="commitment_due",
                utilization_pct=None,
                actual=meta["actual"],
                forecast=meta["forecast"],
                commitment_id=meta.get("commitment_id") or "",
                schedule_line_id=meta.get("schedule_line_id") or "",
                due_date=meta.get("due_date") or "",
                commitment_name=meta.get("commitment_name") or "",
                is_resolved=False,
                email_sent=False,
                fingerprint=fp,
            )
            alert.save()
            by_fp[fp] = alert
        if not alert.is_resolved:
            open_alerts.append(alert)

        if _should_email(alert):
            if _send_alert_email(user, alert):
                alert.email_sent = True
                alert.save()

    for alert in existing_due:
        if alert.fingerprint and alert.fingerprint not in desired and not alert.is_resolved:
            _auto_resolve(alert)

    return open_alerts


def _is_commitment_due_alert(alert) -> bool:
    if (getattr(alert, "alert_type", None) or "") == "commitment_due":
        return True
    if str(getattr(alert, "fingerprint", "") or "").find("|due|") >= 0:
        return True
    if str(getattr(alert, "category_id", "") or "").startswith("commitment:"):
        return True
    return False


def evaluate_risk_alerts(user, report=None) -> list:
    """
    One alert per risk factor in warn (WARN) or high (CRITICAL) state; auto-resolved when the
    factor recovers or risk alerts are turned off. Emailed once when the user allows it.
    """
    from .risk import build_report, get_settings

    uid = _user_id(user)
    settings_obj = get_settings(user)
    alerts_on = settings_obj is None or bool(settings_obj.alerts_enabled)
    desired = {}
    if alerts_on:
        report = report or build_report(user)
        today = date.today()
        for f in report["factors"]:
            if f["status"] not in ("warn", "high"):
                continue
            severity = "CRITICAL" if f["status"] == "high" else "WARN"
            fp = f"{uid}|risk|{f['key']}|{severity}"
            desired[fp] = {
                "year": today.year,
                "month": today.month,
                "category_id": f"risk:{f['key']}",
                "severity": severity,
                "title": f"{'High' if severity == 'CRITICAL' else 'Elevated'} risk: {f['label']}",
                "description": " ".join(x for x in (f["explanation"], f["recommendation"]) if x),
            }

    existing = [a for a in BudgetAlertFS.list_by_user(uid, open_only=False, limit=500) if _is_risk_alert(a)]
    by_fp = {a.fingerprint: a for a in existing if a.fingerprint}
    email_ok = _risk_email_allowed(user, settings_obj)
    open_alerts = []
    for fp, meta in desired.items():
        alert = by_fp.get(fp)
        fields = dict(
            title=meta["title"],
            description=meta["description"],
            severity=meta["severity"],
            year=meta["year"],
            month=meta["month"],
            category_id=meta["category_id"],
            alert_type="risk",
            utilization_pct=None,
            actual=Decimal("0"),
            forecast=Decimal("0"),
        )
        if alert:
            _save_alert_if_changed(alert, **fields, **_open_state_fields(alert))
        else:
            alert = BudgetAlertFS(user_id=uid, is_resolved=False, email_sent=False, fingerprint=fp, **fields)
            alert.save()
            by_fp[fp] = alert
        if not alert.is_resolved:
            open_alerts.append(alert)
        if email_ok and _should_email(alert):
            if _send_risk_email(user, alert):
                alert.email_sent = True
                alert.save()

    for alert in existing:
        if alert.fingerprint and alert.fingerprint not in desired and not alert.is_resolved:
            _auto_resolve(alert)
    return open_alerts


def _risk_email_allowed(user, settings_obj) -> bool:
    if settings_obj is not None and not settings_obj.email_enabled:
        return False
    try:
        from api.user_profile import get_user_profile

        return bool(get_user_profile(user).notify_low_balance)
    except Exception:
        return True


def _send_risk_email(user, alert) -> bool:
    from api.emails import send_risk_alert_email

    if not (getattr(user, "email", None) or "").strip():
        return False
    try:
        return send_risk_alert_email(
            user=user, title=alert.title, description=alert.description or "", severity=alert.severity or "WARN"
        )
    except Exception as e:
        logger.warning("Failed to send risk alert email: %s", e)
        return False


def _is_risk_alert(alert) -> bool:
    return (getattr(alert, "alert_type", None) or "") == "risk" or str(
        getattr(alert, "category_id", "") or ""
    ).startswith("risk:")


def _is_utilization_alert(alert) -> bool:
    # Classify by type: anything else (commitment due dates, risk) must never be
    # auto-resolved by the utilization evaluator. Old rows without a type are utilization.
    alert_type = (getattr(alert, "alert_type", None) or "utilization")
    return alert_type == "utilization" and not _is_commitment_due_alert(alert) and not _is_risk_alert(alert)


def _send_alert_email(user, alert):
    """Send one email for the alert. Returns True if sent, False on hard failure."""
    from api.emails import send_budget_alert_email

    if not (getattr(user, "email", None) or "").strip():
        logger.info(
            "No email for user %s; skipping alert mail fingerprint=%s",
            getattr(user, "pk", "?"),
            alert.fingerprint,
        )
        return False
    try:
        return send_budget_alert_email(
            user=user,
            title=alert.title,
            description=alert.description or "",
            severity=alert.severity or "info",
        )
    except Exception as e:
        logger.warning("Failed to send budget alert email: %s", e)
        return False


def _load_user(uid: str):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    try:
        return User.objects.get(pk=int(uid))
    except Exception:
        try:
            return User.objects.get(pk=uid)
        except Exception:
            return None


def _users_for_alert_processing(user=None):
    """Users who may have budget/commitment alerts (batch job)."""
    if user is not None:
        return [user]

    from django.contrib.auth import get_user_model

    User = get_user_model()
    uids: set[str] = set()
    for c in CommitmentFS.list_all(limit=5000):
        if c.user_id:
            uids.add(str(c.user_id))
    try:
        from budgeting.store import TransactionFS

        for t in TransactionFS.list_all(limit=5000):
            if t.user_id:
                uids.add(str(t.user_id))
    except Exception:
        pass
    for a in BudgetAlertFS.list_all(limit=5000):
        if a.user_id:
            uids.add(str(a.user_id))

    users = []
    for uid in sorted(uids):
        u = _load_user(uid)
        if u and getattr(u, "is_active", True):
            users.append(u)
    if not users and hasattr(User.objects, "filter"):
        users = list(User.objects.filter(is_active=True))
    return users


def send_pending_alert_emails(user) -> int:
    """Email any open alerts not yet sent. Returns count sent."""
    uid = _user_id(user)
    sent = 0
    for alert in BudgetAlertFS.list_by_user(uid, open_only=True, limit=500):
        if not _should_email(alert):
            continue
        if _send_alert_email(user, alert):
            alert.email_sent = True
            alert.save()
            sent += 1
    return sent


def process_budget_alerts(user=None) -> dict:
    """
    Re-evaluate alerts and send emails for all users (or one user).
    Intended for cron / scheduled task — no frontend required.
  """
    today = date.today()
    year, month = today.year, today.month
    stats = {"users": 0, "emails_sent": 0, "errors": 0}

    for u in _users_for_alert_processing(user):
        stats["users"] += 1
        try:
            refresh_alerts_for_user(u, year, month, force=True)
            stats["emails_sent"] += send_pending_alert_emails(u)
        except Exception as e:
            stats["errors"] += 1
            logger.warning("process_budget_alerts failed for user %s: %s", getattr(u, "pk", "?"), e)
    return stats


def _owned_alert(user, alert_pk):
    alert = BudgetAlertFS.get(alert_pk)
    if not alert or alert.user_id != _user_id(user):
        return None
    return alert


def resolve_alert(user, alert_pk):
    """Mark an alert resolved by the user. Returns the alert or None."""
    alert = _owned_alert(user, alert_pk)
    if not alert:
        return None
    alert.is_resolved = True
    alert.resolution = RESOLUTION_USER
    alert.resolved_at = timezone.now()
    alert.snoozed_until = None
    alert.save()
    invalidate_alert_eval_cache(user)
    return alert


def reopen_alert(user, alert_pk):
    """
    Reopen a resolved alert. It stays open until the user resolves it again
    or the next evaluation finds the condition has cleared.
    """
    alert = _owned_alert(user, alert_pk)
    if not alert:
        return None
    alert.is_resolved = False
    alert.resolution = ""
    alert.resolved_at = None
    alert.snoozed_until = None
    alert.save()
    invalidate_alert_eval_cache(user)
    return alert


SNOOZE_DAY_CHOICES = (1, 3, 7)


def snooze_alert(user, alert_pk, days: int):
    """Hide an open alert from the open list, badge and emails for `days` days."""
    alert = _owned_alert(user, alert_pk)
    if not alert or alert.is_resolved:
        return None
    alert.snoozed_until = timezone.now() + timedelta(days=int(days))
    alert.save()
    return alert


def unsnooze_alert(user, alert_pk):
    alert = _owned_alert(user, alert_pk)
    if not alert:
        return None
    alert.snoozed_until = None
    alert.save()
    return alert


def alert_counts(user) -> dict:
    """Counts per lifecycle state for tabs and the nav badge."""
    from .alert_state import alert_state

    counts = {"open": 0, "snoozed": 0, "resolved": 0, "all": 0}
    now = timezone.now()
    for alert in BudgetAlertFS.list_by_user(_user_id(user), open_only=False, limit=500):
        counts[alert_state(alert, now)] += 1
        counts["all"] += 1
    return counts


def open_alert_count(user):
    try:
        return BudgetAlertFS.count_open(_user_id(user))
    except Exception:
        return 0
