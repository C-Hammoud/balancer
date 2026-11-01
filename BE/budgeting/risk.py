"""
Debt & liquidity risk: six factors, a 0-100 score and a level (low / medium / high).

compute_factors() and score() are pure (inputs -> numbers) so they can be tested without data;
gather_inputs() reads the user's data and build_report() puts everything together.

Factors (thresholds are percentages unless noted; every one can be overridden per user):
  debt_to_income        installments due this month / expected monthly income      36 / 50
  overdue_installments  outstanding installments past their due date               any -> high
  balloon_exposure      balloon payments due within the horizon / liquid balance   50 / 100
  debt_to_assets        (liabilities + card debt) / (assets or liquid balance)     50 / 80
  emergency_fund        liquid balance / average monthly spending (months)         < 3 / < 1
  month_cash_flow       money left at month end after known flows                  < 10% of income / < 0
"""
from __future__ import annotations

import calendar
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Optional

from api.currency import convert_if_needed, resolve_report_currency

from . import planned
from .balances import liquid_and_card_totals
from .commitment_schedule import add_months
from .planning import _month_shift, actual_income, commitments_due, expected_income
from .services import _expense_excluded_from_utilization, _user_id, counts_as_expense, envelope_ids_for
from .store import (
    CommitmentFS,
    CommitmentScheduleLineFS,
    FinancialStandingFS,
    RiskSettingsFS,
    RiskSnapshotFS,
    TransactionFS,
)

ZERO = Decimal("0")
HUNDRED = Decimal("100")
HISTORY_MONTHS = 3

DEFAULTS: Dict[str, Decimal] = {
    "dti_warn": Decimal("36"),
    "dti_high": Decimal("50"),
    "balloon_warn": Decimal("50"),
    "balloon_high": Decimal("100"),
    "debt_assets_warn": Decimal("50"),
    "debt_assets_high": Decimal("80"),
    "emergency_warn_months": Decimal("3"),
    "emergency_high_months": Decimal("1"),
    "cash_flow_warn_pct": Decimal("10"),
}
DEFAULT_HORIZON_MONTHS = 6

STATUS_POINTS = {"ok": 100, "warn": 60, "high": 20}
WEIGHTS = {"debt_to_income": 2, "emergency_fund": 2}
FACTOR_KEYS = (
    "debt_to_income",
    "overdue_installments",
    "balloon_exposure",
    "debt_to_assets",
    "emergency_fund",
    "month_cash_flow",
)


# ---- Thresholds -------------------------------------------------------------

def get_settings(user):
    return RiskSettingsFS.get_for_user(_user_id(user))


def resolve_thresholds(settings_obj) -> dict:
    """Defaults with the user's overrides applied (None in an override = use the default)."""
    out = dict(DEFAULTS)
    out["horizon_months"] = DEFAULT_HORIZON_MONTHS
    if settings_obj is None:
        return out
    for key in DEFAULTS:
        value = getattr(settings_obj, key, None)
        if value is not None:
            out[key] = Decimal(str(value))
    if getattr(settings_obj, "horizon_months", None):
        out["horizon_months"] = int(settings_obj.horizon_months)
    return out


# ---- Pure scoring -------------------------------------------------------------

def _q(value: Decimal, places: str = "0.01") -> Decimal:
    return Decimal(value).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _ratio_status(value: Decimal, warn: Decimal, high: Decimal) -> str:
    if value >= high:
        return "high"
    if value >= warn:
        return "warn"
    return "ok"


def _factor(key, category, label, *, value=None, unit="pct", status="unknown", warn_at=None, high_at=None,
            explanation="", recommendation="", items=None) -> dict:
    return {
        "key": key,
        "category": category,
        "label": label,
        "value": value,
        "unit": unit,
        "status": status,
        "warn_at": warn_at,
        "high_at": high_at,
        "explanation": explanation,
        "recommendation": recommendation,
        "items": items or [],
    }


def _debt_to_income(inp: dict, th: dict) -> dict:
    installments = inp.get("installments_month") or ZERO
    income = inp.get("monthly_income")
    f = _factor("debt_to_income", "debt", "Debt payments vs income",
                warn_at=th["dti_warn"], high_at=th["dti_high"], items=inp.get("installment_items") or [])
    if installments <= 0:
        f.update(value=ZERO, status="ok", explanation="No installments are due this month.")
        return f
    if not income or income <= 0:
        f.update(explanation="Add an income stream or record your income so this can be measured.")
        return f
    pct = _q(installments / income * HUNDRED, "0.1")
    f.update(
        value=pct,
        status=_ratio_status(pct, th["dti_warn"], th["dti_high"]),
        explanation=f"Installments due this month take {pct}% of your expected monthly income.",
        recommendation="Avoid new loans and look at refinancing or extending a term to lower the payment."
        if pct >= th["dti_warn"] else "",
    )
    return f


def _overdue(inp: dict, th: dict) -> dict:
    items = inp.get("overdue_items") or []
    total = sum((Decimal(str(i["amount"])) for i in items), ZERO)
    f = _factor("overdue_installments", "debt", "Overdue installments", unit="count",
                value=Decimal(len(items)), high_at=Decimal("1"), items=items)
    if not items:
        f.update(status="ok", explanation="No installment is past its due date.")
    else:
        f.update(
            status="high",
            explanation=f"{len(items)} installment(s) totalling {_q(total)} are past their due date.",
            recommendation="Pay the overdue installments first, or mark them paid if you already did.",
        )
    return f


def _balloon(inp: dict, th: dict) -> dict:
    items = inp.get("balloon_items") or []
    total = sum((Decimal(str(i["amount"])) for i in items), ZERO)
    liquid = inp.get("liquid")
    horizon = th["horizon_months"]
    f = _factor("balloon_exposure", "liquidity", "Upcoming balloon payments",
                warn_at=th["balloon_warn"], high_at=th["balloon_high"], items=items)
    if total <= 0:
        f.update(value=ZERO, status="ok", explanation=f"No balloon payment is due in the next {horizon} months.")
        return f
    if liquid is None:
        f.update(explanation="Add your accounts with their current balance (record it as income) so balloon payments can be compared to your cash.")
        return f
    if liquid <= 0:
        f.update(status="high", explanation=f"Balloon payments of {_q(total)} are due and your liquid balance is {_q(liquid)}.",
                 recommendation="Start setting money aside now or arrange refinancing before the due date.")
        return f
    pct = _q(total / liquid * HUNDRED, "0.1")
    f.update(
        value=pct,
        status=_ratio_status(pct, th["balloon_warn"], th["balloon_high"]),
        explanation=f"Balloon payments of {_q(total)} due in the next {horizon} months equal {pct}% of your liquid balance.",
        recommendation="Set money aside each month for the balloon, or arrange refinancing early."
        if pct >= th["balloon_warn"] else "",
    )
    return f


def _debt_to_assets(inp: dict, th: dict) -> dict:
    standing = inp.get("standing")
    card_debt = inp.get("card_debt") or ZERO
    liabilities = (standing["liabilities"] if standing else ZERO) + card_debt
    assets = standing["assets"] if standing and standing["assets"] > 0 else inp.get("liquid")
    f = _factor("debt_to_assets", "debt", "Debt vs assets", warn_at=th["debt_assets_warn"], high_at=th["debt_assets_high"])
    if liabilities <= 0:
        if standing is None and inp.get("liquid") is None:
            f.update(explanation="Record your assets and liabilities (net worth) to measure this.")
        else:
            f.update(value=ZERO, status="ok", explanation="You have no recorded debt.")
        return f
    if assets is None or assets <= 0:
        f.update(status="high", explanation=f"You owe {_q(liabilities)} with no recorded assets to cover it.",
                 recommendation="Record your assets in Net worth, and focus on paying down debt.")
        return f
    pct = _q(liabilities / assets * HUNDRED, "0.1")
    f.update(
        value=pct,
        status=_ratio_status(pct, th["debt_assets_warn"], th["debt_assets_high"]),
        explanation=f"Your debts ({_q(liabilities)}) equal {pct}% of your assets ({_q(assets)}).",
        recommendation="Pay down the most expensive debt first (credit cards) before taking on more."
        if pct >= th["debt_assets_warn"] else "",
    )
    return f


def _emergency(inp: dict, th: dict) -> dict:
    liquid = inp.get("liquid")
    spending = inp.get("avg_spending")
    warn, high = th["emergency_warn_months"], th["emergency_high_months"]
    f = _factor("emergency_fund", "liquidity", "Emergency fund", unit="months", warn_at=warn, high_at=high)
    if liquid is None:
        f.update(explanation="Add your accounts with their current balance (record it as income) to see how long your cash would last.")
        return f
    if not spending or spending <= 0:
        f.update(explanation=f"Record a few months of expenses to measure how long your cash would last.")
        return f
    raw = max(liquid, ZERO) / spending
    months = _q(raw, "0.1")
    status = "high" if raw < high else "warn" if raw < warn else "ok"
    f.update(
        value=months,
        status=status,
        explanation=f"Your liquid balance would cover {months} month(s) of your usual spending ({_q(spending)} a month).",
        recommendation=f"Build savings up to at least {warn} months of spending." if status != "ok" else "",
    )
    return f


def _cash_flow(inp: dict, th: dict) -> dict:
    liquid = inp.get("liquid")
    f = _factor("month_cash_flow", "liquidity", "This month's cash flow", unit="money",
                warn_at=th["cash_flow_warn_pct"], high_at=ZERO, items=inp.get("cash_flow_items") or [])
    if liquid is None:
        f.update(explanation="Add your accounts with their current balance (record it as income) to project this month's cash flow.")
        return f
    projected = (
        liquid
        + (inp.get("inflows_left") or ZERO)
        - (inp.get("installments_left") or ZERO)
        - (inp.get("planned_out_left") or ZERO)
        - (inp.get("discretionary_left") or ZERO)
    )
    projected = _q(projected)
    income = inp.get("monthly_income")
    cushion = _q(income * th["cash_flow_warn_pct"] / HUNDRED) if income and income > 0 else None
    if projected < 0:
        status = "high"
    elif cushion is not None and projected < cushion:
        status = "warn"
    else:
        status = "ok"
    f.update(
        value=projected,
        status=status,
        explanation=f"At the current pace you would end the month with about {projected}.",
        recommendation=(
            "Cut discretionary spending or move a planned expense to next month to stay positive."
            if status == "high"
            else "Keep discretionary spending low until your next income arrives." if status == "warn" else ""
        ),
    )
    return f


def compute_factors(inputs: dict, thresholds: dict) -> List[dict]:
    th = dict(DEFAULTS, horizon_months=DEFAULT_HORIZON_MONTHS)
    th.update(thresholds or {})
    return [
        _debt_to_income(inputs, th),
        _overdue(inputs, th),
        _balloon(inputs, th),
        _debt_to_assets(inputs, th),
        _emergency(inputs, th),
        _cash_flow(inputs, th),
    ]


def score(factors: List[dict]) -> tuple:
    """(score 0-100 or None, level). Unknown factors are left out; two factors count double."""
    total, weight = 0, 0
    for f in factors:
        points = STATUS_POINTS.get(f["status"])
        if points is None:
            continue
        w = WEIGHTS.get(f["key"], 1)
        total += points * w
        weight += w
    if not weight:
        return None, "unknown"
    value = int((Decimal(total) / Decimal(weight)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    level = "low" if value >= 70 else "medium" if value >= 40 else "high"
    return value, level


# ---- Inputs from the user's data -------------------------------------------------

def _month_bounds(d: date) -> tuple:
    return date(d.year, d.month, 1), date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def _monthly_income(user, currency: str, today: date) -> tuple:
    """Expected income (streams + recurring planned income), else the recent average actual income."""
    recurring = [i for i in planned.active_items(user, "income") if i.frequency != "once"]
    expected = expected_income(user, currency) + planned.recurring_monthly_total(recurring, currency)
    if expected > 0:
        return expected, "expected"
    # No streams: average of the months that had income, this month included, so income you
    # record today counts right away (a month already above the average raises it).
    totals = []
    for back in range(0, HISTORY_MONTHS + 1):
        y, m = _month_shift(today.year, today.month, -back)
        amount = actual_income(user, y, m, currency)
        if amount > 0:
            totals.append(amount)
    if totals:
        return sum(totals, ZERO) / len(totals), "recent_average"
    return None, "missing"


def _avg_spending(uid: str, currency: str, today: date) -> Optional[Decimal]:
    totals = []
    for back in range(1, HISTORY_MONTHS + 1):
        y, m = _month_shift(today.year, today.month, -back)
        amount = sum(
            (
                convert_if_needed(t.amount or ZERO, getattr(t, "currency", None) or "USD", currency)
                for t in TransactionFS.list_by_user(uid, month=f"{y}-{m:02d}", limit=5000)
                if counts_as_expense(t)
            ),
            ZERO,
        )
        if amount > 0:
            totals.append(amount)
    return sum(totals, ZERO) / len(totals) if totals else None


def _commitment_inputs(uid: str, currency: str, today: date, horizon_months: int) -> dict:
    _, month_end = _month_bounds(today)
    horizon_end = add_months(today, horizon_months)
    overdue, balloons, installments_left = [], [], ZERO
    for c in CommitmentFS.list_by_user(uid):
        c_cur = getattr(c, "currency", None) or "USD"
        lines = CommitmentScheduleLineFS.list_by_commitment(c.pk, cleanup_duplicates=False)
        last = lines[-1] if lines else None
        balloon = Decimal(getattr(c, "balloon", 0) or 0)
        for line in lines:
            if line.status != "outstanding" or not line.due_date:
                continue
            amount = convert_if_needed(line.amount or ZERO, c_cur, currency)
            if line.due_date < today:
                overdue.append({"commitment_id": c.pk, "name": c.name, "due_date": line.due_date.isoformat(),
                                "amount": _q(amount), "schedule_line_id": line.pk})
            elif line.due_date <= month_end:
                installments_left += amount
            if line is last and balloon > 0 and today <= line.due_date <= horizon_end:
                balloons.append({"commitment_id": c.pk, "name": c.name, "due_date": line.due_date.isoformat(),
                                 "amount": _q(convert_if_needed(balloon, c_cur, currency))})
    return {"overdue_items": overdue, "balloon_items": balloons, "installments_left": installments_left}


def _sub_budgets_due(user, today: date, month_end: date, currency: str) -> tuple:
    """Plan sub-budgets (trips...) taking place in the rest of this month: their unspent money goes out."""
    from . import sub_budgets

    total, items = ZERO, []
    try:
        budgets = sub_budgets.in_plan_budgets(user)
    except Exception:
        return ZERO, []
    for b in budgets:
        starts = b.start_date or today
        ends = b.end_date or starts
        if starts > month_end or ends < today:
            continue
        budgeted = convert_if_needed(Decimal(b.total_amount or 0), b.currency or "USD", currency)
        left = max(budgeted - sub_budgets.spent(b, currency), ZERO)
        if left > 0:
            total += left
            items.append({"id": str(b.pk), "name": b.name, "kind": "sub_budget", "amount": _q(left),
                          "dates": [starts.isoformat()], "is_essential": False})
    return total, items


def gather_inputs(user, currency: str, thresholds: dict, settings_obj=None, today: Optional[date] = None) -> dict:
    today = today or date.today()
    uid = _user_id(user)
    month_start, month_end = _month_bounds(today)
    tomorrow = today + timedelta(days=1)

    income, income_source = _monthly_income(user, currency, today)
    installments_month, installment_items = commitments_due(user, today.year, today.month, currency)

    included = list(getattr(settings_obj, "included_account_ids", None) or [])
    totals = liquid_and_card_totals(user, currency, included)
    # Without accounts, or when money never entered them (no income or opening balance
    # recorded), the balances only measure spending: liquidity is unknown, not negative.
    known = bool(totals["accounts"]) and totals["has_inflows"]
    liquid = totals["liquid"] if known else None

    standing = None
    standings = FinancialStandingFS.list_by_user(uid)
    if standings:
        s = standings[0]
        standing = {
            "as_of": s.snapshot_date.isoformat() if s.snapshot_date else None,
            "assets": Decimal(s.total_assets or 0),
            "liabilities": Decimal(s.total_liabilities or 0),
        }

    commitment = _commitment_inputs(uid, currency, today, int(thresholds.get("horizon_months") or DEFAULT_HORIZON_MONTHS))

    # This month so far: income received and discretionary spending pace.
    received = actual_income(user, today.year, today.month, currency)
    spent = ZERO
    envelopes = envelope_ids_for(user)
    for t in TransactionFS.list_by_user(uid, month=f"{today.year}-{today.month:02d}", limit=5000):
        # Sub-budget spending (a trip) is planned: it is counted below, not in the everyday pace.
        if counts_as_expense(t) and not _expense_excluded_from_utilization(t, envelopes) and t.date and t.date <= today:
            spent += convert_if_needed(t.amount or ZERO, getattr(t, "currency", None) or "USD", currency)
    days_in_month = month_end.day
    days_left = days_in_month - today.day
    discretionary_left = spent / today.day * days_left if today.day else ZERO

    stream_income = expected_income(user, currency)
    planned_in, planned_in_items = planned.total_between(planned.active_items(user, "income"), tomorrow, month_end, currency)
    planned_out, planned_out_items = planned.total_between(planned.active_items(user, "expense"), tomorrow, month_end, currency)
    trip_out, trip_items = _sub_budgets_due(user, today, month_end, currency)
    planned_out += trip_out
    planned_out_items += trip_items
    inflows_left = max(stream_income - received, ZERO) + planned_in

    return {
        "as_of": today,
        "currency": currency,
        "monthly_income": income,
        "income_source": income_source,
        "installments_month": installments_month,
        "installment_items": [{**i, "amount": _q(i["amount"])} for i in installment_items],
        "liquid": liquid,
        "card_debt": totals["card_debt"],
        "liquid_account_ids": totals["liquid_account_ids"],
        "standing": standing,
        "avg_spending": _avg_spending(uid, currency, today),
        "inflows_left": inflows_left,
        "installments_left": commitment["installments_left"],
        "planned_out_left": planned_out,
        "discretionary_left": discretionary_left,
        "cash_flow_items": planned_in_items + planned_out_items,
        "overdue_items": commitment["overdue_items"],
        "balloon_items": commitment["balloon_items"],
    }


def _money(value) -> Optional[str]:
    return None if value is None else str(_q(value))


def _json_factor(f: dict) -> dict:
    out = dict(f)
    for key in ("value", "warn_at", "high_at"):
        if out[key] is not None:
            out[key] = str(out[key])
    out["items"] = [{k: (str(v) if isinstance(v, Decimal) else v) for k, v in item.items()} for item in f["items"]]
    return out


def build_report(user, currency: Optional[str] = None, *, save_snapshot: bool = True, today: Optional[date] = None) -> dict:
    today = today or date.today()
    currency = currency or resolve_report_currency(user, None)
    settings_obj = get_settings(user)
    th = resolve_thresholds(settings_obj)
    inputs = gather_inputs(user, currency, th, settings_obj, today)
    factors = compute_factors(inputs, th)
    value, level = score(factors)
    report = {
        "as_of": today.isoformat(),
        "currency": currency,
        "score": value,
        "level": level,
        "factors": [_json_factor(f) for f in factors],
        "missing": [f["explanation"] for f in factors if f["status"] == "unknown"],
        "inputs": {
            "monthly_income": _money(inputs["monthly_income"]),
            "income_source": inputs["income_source"],
            "installments_month": _money(inputs["installments_month"]),
            "liquid": _money(inputs["liquid"]),
            "card_debt": _money(inputs["card_debt"]),
            "avg_spending": _money(inputs["avg_spending"]),
            "inflows_left": _money(inputs["inflows_left"]),
            "installments_left": _money(inputs["installments_left"]),
            "planned_out_left": _money(inputs["planned_out_left"]),
            "discretionary_left": _money(inputs["discretionary_left"]),
            "liquid_account_ids": inputs["liquid_account_ids"],
            "standing_as_of": inputs["standing"]["as_of"] if inputs["standing"] else None,
        },
        "thresholds": {k: str(v) for k, v in th.items()},
    }
    if save_snapshot:
        save_daily_snapshot(user, report, today)
    return report


def save_daily_snapshot(user, report: dict, today: date):
    uid = _user_id(user)
    snap = RiskSnapshotFS.get_for_day(uid, today) or RiskSnapshotFS(user_id=uid, as_of=today)
    snap.score = report["score"]
    snap.level = report["level"]
    snap.factors = [{"key": f["key"], "status": f["status"], "value": f["value"]} for f in report["factors"]]
    snap.save()
    return snap


def history(user, days: int = 90, today: Optional[date] = None) -> List[dict]:
    today = today or date.today()
    since = today - timedelta(days=max(1, min(int(days), 730)))
    return [
        {"as_of": s.as_of.isoformat(), "score": s.score, "level": s.level}
        for s in RiskSnapshotFS.list_since(_user_id(user), since)
    ]
