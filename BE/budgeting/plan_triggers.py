"""
When to suggest a new budget plan, and how the user is told (in-app notification + email).

Run daily: `python manage.py review_budget_plans`. Commitment changes trigger immediately.
Each (user, month, reason) notifies at most once (Notification.fingerprint).
"""
import calendar
import logging
from datetime import date
from decimal import Decimal

from api.currency import convert_if_needed, resolve_report_currency

from . import planning
from .services import _expense_excluded_from_utilization, _user_id, envelope_ids_for
from .store import BudgetPlanFS, NotificationFS, TransactionFS

logger = logging.getLogger(__name__)
INCOME_DRIFT = Decimal("0.10")      # actual vs expected income
OVERSPEND_RATIO = Decimal("0.80")   # projected savings below 80% of planned
OVERSPEND_FROM_DAY = 15


def _settings(user):
    from api.user_profile import get_user_profile

    profile = get_user_profile(user)
    return bool(profile.notify_plan_updates), int(profile.savings_target_pct)


def _preferred_type(user, has_history: bool) -> str:
    accepted = [p for p in BudgetPlanFS.list_by_user(_user_id(user), limit=50) if p.status == "accepted"]
    if accepted:
        return accepted[0].plan_type
    return "spending_based" if has_history else "rule_50_30_20"


def _notify(user, *, kind, title, body, link, related_id, fingerprint, plan=None) -> bool:
    uid = _user_id(user)
    if NotificationFS.exists_fingerprint(uid, fingerprint):
        return False
    NotificationFS(user_id=uid, kind=kind, title=title, body=body, link=link,
                   related_id=related_id or "", fingerprint=fingerprint).save()
    if plan is not None:
        from api.emails import send_plan_suggestion_email

        try:
            send_plan_suggestion_email(user=user, plan=plan, headline=title, intro=body, link_path=link)
        except Exception:
            logger.warning("Plan suggestion email failed for user %s", uid, exc_info=True)
    return True


def suggest_plan(user, year: int, month: int, *, reason: str, title: str, body: str, fingerprint: str) -> bool:
    """Save a suggested plan and notify. Returns True if a notification was sent."""
    enabled, pct = _settings(user)
    uid = _user_id(user)
    if not enabled or NotificationFS.exists_fingerprint(uid, fingerprint):
        return False
    currency = resolve_report_currency(user)
    if planning.expected_income(user, currency) <= 0:
        return _notify(
            user, kind="plan_needs_income", title="Add your income to get a budget plan",
            body="Enter your expected monthly income and we will suggest a plan that covers your commitments.",
            link="/budgeting/plan", related_id="", fingerprint=f"{uid}|needs-income|{year}-{month:02d}",
        )
    _, months_used = planning.spending_by_group(user, year, month, currency)
    plan = planning.build_plan(user, year, month, _preferred_type(user, months_used > 0), currency, savings_pct=pct)
    obj = planning.save_plan(user, plan, reason=reason)
    plan = planning.plan_to_dict(obj)
    return _notify(user, kind="plan_suggested", title=title, body=body, link=f"/budgeting/plan?id={obj.pk}",
                   related_id=obj.pk, fingerprint=fingerprint, plan=plan)


def check_monthly(user, today: date) -> bool:
    uid = _user_id(user)
    existing = BudgetPlanFS.list_for_month(uid, today.year, today.month)
    if any(p.status in ("suggested", "accepted") for p in existing):
        return False
    label = f"{calendar.month_name[today.month]} {today.year}"
    return suggest_plan(
        user, today.year, today.month, reason="monthly",
        title=f"Your budget plan for {label} is ready",
        body=f"Here is a suggested plan for {label} based on your income and the commitments due this month.",
        fingerprint=f"{uid}|{today.year}-{today.month:02d}|monthly",
    )


def check_income_change(user, today: date) -> bool:
    """Last full month's actual income differs from the expected income by more than 10%."""
    currency = resolve_report_currency(user)
    expected = planning.expected_income(user, currency)
    py, pm = planning._month_shift(today.year, today.month, -1)
    actual = planning.actual_income(user, py, pm, currency)
    if expected <= 0 or actual <= 0 or abs(actual - expected) / expected <= INCOME_DRIFT:
        return False
    uid = _user_id(user)
    more_or_less = "more" if actual > expected else "less"
    return suggest_plan(
        user, today.year, today.month, reason="income_change",
        title="Your income changed: review your budget plan",
        body=(
            f"You received {actual:,.0f} {currency} in {calendar.month_name[pm]}, {more_or_less} than the "
            f"{expected:,.0f} {currency} you expect. Update your income if this is the new normal, "
            "and review the updated plan."
        ),
        fingerprint=f"{uid}|{today.year}-{today.month:02d}|income_change",
    )


def check_overspending(user, today: date) -> bool:
    """From mid-month: at the current pace, savings will fall below 80% of the accepted plan."""
    if today.day < OVERSPEND_FROM_DAY or not _settings(user)[0]:
        return False
    uid = _user_id(user)
    accepted = [p for p in BudgetPlanFS.list_for_month(uid, today.year, today.month) if p.status == "accepted"]
    if not accepted:
        return False
    plan = planning.plan_to_dict(accepted[0])
    planned_savings = plan["savings_amount"]
    if planned_savings <= 0:
        return False
    envelopes = envelope_ids_for(user)
    spent = sum(
        (
            convert_if_needed(t.amount or 0, getattr(t, "currency", None) or "USD", plan["currency"])
            for t in TransactionFS.list_by_user(uid, month=f"{today.year}-{today.month:02d}", limit=5000)
            if t.direction == "expense" and not _expense_excluded_from_utilization(t, envelopes)
        ),
        Decimal("0"),
    )
    days = calendar.monthrange(today.year, today.month)[1]
    # Sub-budget money (a trip...) is reserved, so it is not savings either.
    projected_savings = (
        plan["available"] - spent / today.day * days - plan["invested_total"] - plan.get("reserved_total", 0)
    )
    if projected_savings >= planned_savings * OVERSPEND_RATIO:
        return False
    return _notify(
        user, kind="plan_overspending", title="You are spending faster than planned",
        body=(
            f"At this pace you will save about {max(projected_savings, 0):,.0f} {plan['currency']} this month "
            f"instead of {planned_savings:,.0f}. Check which categories are running ahead."
        ),
        link=f"/budgeting/plan?id={accepted[0].pk}", related_id=accepted[0].pk,
        fingerprint=f"{uid}|{today.year}-{today.month:02d}|overspending",
    )


def on_commitment_change(user, commitment_id: str, action: str, name: str = "") -> bool:
    """Called from the commitment views: the month's fixed costs changed."""
    today = date.today()
    uid = _user_id(user)
    what = {"created": "added", "deleted": "removed", "updated": "changed"}.get(action, "changed")
    label = name or "your loan"
    try:
        return suggest_plan(
            user, today.year, today.month, reason="commitment_change",
            title="Commitments changed: updated budget plan",
            body=f"The commitment {label} was {what}, so the money left after commitments changed. "
                 "Here is an updated plan.",
            fingerprint=f"{uid}|{today.year}-{today.month:02d}|commitment|{commitment_id}|{action}",
        )
    except Exception:
        logger.warning("Plan suggestion after commitment change failed for user %s", uid, exc_info=True)
        return False


def review_user(user, today: date | None = None) -> dict:
    today = today or date.today()
    return {
        "monthly": check_monthly(user, today),
        "income_change": check_income_change(user, today),
        "overspending": check_overspending(user, today),
    }
