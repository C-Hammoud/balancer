"""
Budget planning engine: income - commitments -> suggested monthly budgets and savings.

Every plan keeps one invariant: savings_amount = available - sum(line amounts), where
available = expected income - commitment installments due that month. Bucket totals are
derived from the lines, so edited plans stay consistent.
"""
import calendar
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from api.currency import convert_if_needed

from .category_access import visible_categories, visible_groups
from .services import _expense_excluded_from_utilization, _user_id, counts_as_income, envelope_ids_for
from .sub_budgets import plan_lines as sub_budget_lines
from .store import (
    BudgetFS,
    BudgetPlanFS,
    CommitmentFS,
    CommitmentScheduleLineFS,
    GroupBucketFS,
    IncomeStreamFS,
    TransactionFS,
)

PLAN_TYPES = ("rule_50_30_20", "spending_based")
PLAN_LABELS = {"rule_50_30_20": "50/30/20", "spending_based": "Based on your spending"}
BUCKETS = ("needs", "wants", "savings")
ZERO = Decimal("0")
HISTORY_MONTHS = 3
MAX_WANTS_TRIM = Decimal("0.30")  # spending-based plan trims each "want" by at most 30%

# Group names that usually hold essentials (used until the user classifies a group).
NEEDS_KEYWORDS = (
    "home", "house", "housing", "rent", "mortgage", "utilit", "electric", "water", "gas", "internet",
    "phone", "grocer", "food", "supermarket", "transport", "fuel", "car", "health", "medical",
    "pharmacy", "insurance", "education", "school", "tuition", "child", "loan", "debt",
)
_FREQ_PER_MONTH = {
    "monthly": Decimal("1"),
    "weekly": Decimal("52") / Decimal("12"),
    "biweekly": Decimal("26") / Decimal("12"),
    "yearly": Decimal("1") / Decimal("12"),
}


def round_step(currency: str) -> Decimal:
    return Decimal("1000") if (currency or "").upper() == "LBP" else Decimal("1")


def money_round(value: Decimal, currency: str) -> Decimal:
    step = round_step(currency)
    return ((Decimal(value) / step).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * step).quantize(
        Decimal("0.01")
    )


def _month_shift(year: int, month: int, delta: int) -> tuple:
    idx = year * 12 + (month - 1) + delta
    return idx // 12, idx % 12 + 1


# ---- Inputs -----------------------------------------------------------------

def stream_monthly_amount(stream) -> Decimal:
    return Decimal(stream.amount or 0) * _FREQ_PER_MONTH.get(stream.frequency or "monthly", Decimal("1"))


def expected_income(user, currency: str) -> Decimal:
    total = ZERO
    for s in IncomeStreamFS.list_by_user(_user_id(user)):
        if s.is_active:
            total += convert_if_needed(stream_monthly_amount(s), s.currency or "USD", currency)
    return total


def actual_income(user, year: int, month: int, currency: str) -> Decimal:
    month_str = f"{year}-{month:02d}"
    return sum(
        (
            convert_if_needed(t.amount or ZERO, getattr(t, "currency", None) or "USD", currency)
            for t in TransactionFS.list_by_user(_user_id(user), month=month_str, limit=5000)
            if counts_as_income(t)
        ),
        ZERO,
    )


def commitments_due(user, year: int, month: int, currency: str) -> tuple:
    """All installments due in the month (paid or not): they are fixed costs of that month."""
    start = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    total, items = ZERO, []
    for c in CommitmentFS.list_by_user(_user_id(user)):
        amount = ZERO
        for line in CommitmentScheduleLineFS.list_by_commitment(c.pk):
            if line.due_date and start <= line.due_date <= end:
                amount += convert_if_needed(line.amount, getattr(c, "currency", None) or "USD", currency)
        if amount:
            total += amount
            items.append({"commitment_id": c.pk, "name": c.name, "amount": amount})
    return total, items


def default_bucket(group_name: str) -> str:
    name = (group_name or "").lower()
    return "needs" if any(k in name for k in NEEDS_KEYWORDS) else "wants"


def group_buckets(user, groups) -> dict:
    saved = {b.group_id: b.bucket for b in GroupBucketFS.list_by_user(_user_id(user))}
    return {g.pk: saved.get(g.pk) or default_bucket(g.name) for g in groups}


def plannable_groups(user) -> list:
    """Visible groups that have at least one reported subcategory (budgets are per group)."""
    cats = [c for c in visible_categories(user) if c.include_in_reports]
    with_subs = {c.group_id for c in cats}
    groups = [g for g in visible_groups(user) if g.pk in with_subs]
    return sorted(groups, key=lambda g: (g.order, g.name.lower()))


def spending_by_group(user, year: int, month: int, currency: str, months: int = HISTORY_MONTHS) -> tuple:
    """
    Average monthly spending per group over the `months` full months before (year, month).
    Commitment installments and plan sub-budget expenses (a trip...) are excluded: both are
    planned separately.
    Returns (averages_by_group_id, months_with_data).
    """
    cat_group = {c.pk: c.group_id for c in visible_categories(user)}
    uid = _user_id(user)
    envelopes = envelope_ids_for(user)
    totals, months_with_data = {}, 0
    for back in range(1, months + 1):
        y, m = _month_shift(year, month, -back)
        found = False
        for t in TransactionFS.list_by_user(uid, month=f"{y}-{m:02d}", limit=5000):
            if t.direction != "expense" or _expense_excluded_from_utilization(t, envelopes):
                continue
            gid = cat_group.get(t.category_id or "")
            if not gid:
                continue
            found = True
            amt = convert_if_needed(t.amount or ZERO, getattr(t, "currency", None) or "USD", currency)
            totals[gid] = totals.get(gid, ZERO) + amt
        months_with_data += 1 if found else 0
    if not months_with_data:
        return {}, 0
    return {gid: v / months_with_data for gid, v in totals.items()}, months_with_data


def current_forecasts(user, year: int, month: int) -> dict:
    """Effective forecast per group: explicit group budget, else the sum of subcategory budgets."""
    cat_group = {c.pk: c.group_id for c in visible_categories(user)}
    explicit, from_subs = {}, {}
    for b in BudgetFS.list_by_user(_user_id(user), year=year, month=month):
        if (b.category_id or "").strip():
            gid = cat_group.get(b.category_id)
            if gid:
                from_subs[gid] = from_subs.get(gid, ZERO) + (b.forecast or ZERO)
        elif (b.group_id or "").strip():
            explicit[b.group_id] = b.forecast or ZERO
    return {gid: (v if v > 0 else from_subs.get(gid, ZERO)) for gid, v in {**from_subs, **explicit}.items()}


# ---- Allocation -------------------------------------------------------------

def _split(total: Decimal, group_ids: list, weights: dict) -> dict:
    """Split `total` across groups in proportion to weights (equal when no weights)."""
    if not group_ids or total <= 0:
        return {gid: ZERO for gid in group_ids}
    w = {gid: max(weights.get(gid, ZERO), ZERO) for gid in group_ids}
    wsum = sum(w.values(), ZERO)
    if wsum <= 0:
        return {gid: total / len(group_ids) for gid in group_ids}
    return {gid: total * w[gid] / wsum for gid in group_ids}


def _pct(part: Decimal, whole: Decimal) -> int:
    return int((part / whole * 100).quantize(Decimal("1"))) if whole > 0 else 0


def _rule_50_30_20(income, commitments, available, buckets, history, warnings) -> dict:
    """Commitments count as needs. If they crowd out living costs, shift to 60/25/15."""
    ids = {b: [g for g, bk in buckets.items() if bk == b] for b in BUCKETS}
    hist_needs = sum((history.get(g, ZERO) for g in ids["needs"]), ZERO)
    needs_r, wants_r, save_r = Decimal("0.50"), Decimal("0.30"), Decimal("0.20")
    floor = max(hist_needs, income * Decimal("0.15"))
    if income * needs_r - commitments < floor:
        needs_r, wants_r, save_r = Decimal("0.60"), Decimal("0.25"), Decimal("0.15")
        warnings.append(
            f"Commitments take {_pct(commitments, income)}% of income, so this plan uses a "
            "debt-aware 60/25/15 split instead of 50/30/20."
        )
    needs_left = income * needs_r - commitments
    wants = income * wants_r
    if needs_left < floor:
        # Still too tight: protect living costs, keep a 5% savings floor, squeeze wants.
        needs_left = floor
        wants = max(available - needs_left - income * Decimal("0.05"), ZERO)
        warnings.append("Income after commitments is tight: wants are reduced to keep essentials covered.")
    alloc = {}
    alloc.update(_split(max(needs_left, ZERO), ids["needs"], history))
    alloc.update(_split(wants, ids["wants"], history))
    # Groups the user marked "savings" (e.g. investments) keep their usual amount from the savings share.
    save_share = income * save_r
    for gid in ids["savings"]:
        alloc[gid] = min(history.get(gid, ZERO), save_share)
        save_share -= alloc[gid]
    return {gid: (v, "rule") for gid, v in alloc.items()}


def _spending_based(income, available, buckets, history, savings_pct, warnings) -> dict:
    """Start from recent averages; trim wants (max 30% each) to reach the savings target."""
    target = income * Decimal(savings_pct) / 100
    alloc = {gid: (history.get(gid, ZERO), "history") for gid in buckets}
    spend = sum((v for v, _ in alloc.values()), ZERO)
    shortfall = spend + target - available
    if shortfall > 0:
        wants = {g: alloc[g][0] for g, b in buckets.items() if b == "wants" and alloc[g][0] > 0}
        max_trim = sum(wants.values(), ZERO) * MAX_WANTS_TRIM
        trim = min(shortfall, max_trim)
        for gid, amt in _split(trim, list(wants), wants).items():
            alloc[gid] = (alloc[gid][0] - amt, "trimmed")
        if trim:
            warnings.append(f"Wants are trimmed to move closer to your {savings_pct}% savings target.")
        if shortfall - trim > 0:
            warnings.append(
                f"Your usual spending leaves less than your {savings_pct}% savings target even after trimming wants."
            )
    return alloc


def build_plan(user, year: int, month: int, plan_type: str, currency: str, savings_pct: int = 20) -> dict:
    """Compute a plan (not saved). Amounts are Decimals in `currency`."""
    if plan_type not in PLAN_TYPES:
        raise ValueError("Unknown plan type.")
    warnings = []
    income = expected_income(user, currency)
    commitments, commitment_items = commitments_due(user, year, month, currency)
    available = income - commitments
    groups = plannable_groups(user)
    buckets = group_buckets(user, groups)
    history, months_used = spending_by_group(user, year, month, currency)
    current = current_forecasts(user, year, month)

    effective_type = plan_type
    if income <= 0:
        warnings.append("Add your expected income to get a plan.")
        alloc = {g.pk: (ZERO, "rule") for g in groups}
    elif plan_type == "spending_based" and not months_used:
        warnings.append("No spending history in the last 3 months yet, so this uses the 50/30/20 split.")
        effective_type = "rule_50_30_20"
        alloc = _rule_50_30_20(income, commitments, available, buckets, history, warnings)
    elif plan_type == "spending_based":
        alloc = _spending_based(income, available, buckets, history, savings_pct, warnings)
    else:
        alloc = _rule_50_30_20(income, commitments, available, buckets, history, warnings)

    lines = []
    for g in groups:
        amount, basis = alloc.get(g.pk, (ZERO, "rule"))
        lines.append({
            "group_id": g.pk,
            "group_name": g.name,
            "bucket": buckets[g.pk],
            "amount": money_round(max(amount, ZERO), currency),
            "average_spend": money_round(history.get(g.pk, ZERO), currency),
            "current_forecast": current.get(g.pk, ZERO),
            "basis": basis,
        })
    if commitments > 0 and income > 0 and commitments >= income:
        warnings.append("Commitments due this month are more than your income.")
    plan = {
        "year": year,
        "month": month,
        "plan_type": plan_type,
        "effective_type": effective_type,
        "label": PLAN_LABELS[plan_type],
        "currency": currency,
        "income_total": money_round(income, currency),
        "commitments_total": money_round(commitments, currency),
        "commitments": [{**c, "amount": money_round(c["amount"], currency)} for c in commitment_items],
        "history_months": months_used,
        "savings_target_pct": savings_pct,
        "lines": lines,
        "warnings": warnings,
        # Trips / projects attached to the plan: their money is reserved before savings.
        "sub_budgets": sub_budget_lines(user, year, month, currency),
    }
    plan = recompute_totals(plan)
    if plan["savings_amount"] < 0 and plan["reserved_total"] > 0:
        warnings.append(
            f"Your sub-budgets need {money_round(-plan['savings_amount'], currency)} {currency} more than this "
            "month's available money. Lower a sub-budget, spread it over more months, or trim a budget line."
        )
    return plan


def recompute_totals(plan: dict) -> dict:
    """Derive available, bucket totals and savings from income, commitments and lines."""
    income = Decimal(str(plan["income_total"]))
    commitments = Decimal(str(plan["commitments_total"]))
    plan["available"] = income - commitments
    totals = {b: ZERO for b in BUCKETS}
    for line in plan["lines"]:
        line["amount"] = Decimal(str(line["amount"]))
        totals[line["bucket"] if line["bucket"] in totals else "wants"] += line["amount"]
    plan["needs_total"] = totals["needs"]
    plan["wants_total"] = totals["wants"]
    # Budgets for groups the user marked "savings" (investments, deposits) are money saved too.
    plan["invested_total"] = totals["savings"]
    subs = plan.get("sub_budgets") or []
    for sub in subs:
        sub["amount"] = Decimal(str(sub["amount"]))
    plan["sub_budgets"] = subs
    plan["reserved_total"] = sum((sub["amount"] for sub in subs), ZERO).quantize(Decimal("0.01"))
    # Main budget = available; it funds the group lines, the sub-budgets, and what is left is savings.
    plan["savings_amount"] = plan["available"] - sum(totals.values(), ZERO) - plan["reserved_total"]
    plan["savings_pct"] = _pct(max(plan["savings_amount"] + totals["savings"], ZERO), income)
    return plan


# ---- Persistence ------------------------------------------------------------

def _json_lines(lines: list) -> list:
    return [
        {**line, **{k: str(line[k]) for k in ("amount", "average_spend", "current_forecast") if k in line}}
        for line in lines
    ]


def _json_sub_budgets(subs: list) -> list:
    keys = ("amount", "total", "funded_before", "spent")
    return [{**sub, **{k: str(sub[k]) for k in keys if k in sub}} for sub in subs]


def save_plan(user, plan: dict, reason: str = "manual"):
    """Store a computed plan as a suggestion; replaces older pending suggestions for that month."""
    uid = _user_id(user)
    for old in BudgetPlanFS.list_for_month(uid, plan["year"], plan["month"]):
        if old.status == "suggested":
            old.status = "superseded"
            old.save()
    obj = BudgetPlanFS(
        user_id=uid,
        year=plan["year"],
        month=plan["month"],
        plan_type=plan["plan_type"],
        status="suggested",
        reason=reason,
        currency=plan["currency"],
        income_total=plan["income_total"],
        commitments_total=plan["commitments_total"],
        available=plan["available"],
        needs_total=plan["needs_total"],
        wants_total=plan["wants_total"],
        savings_amount=plan["savings_amount"],
        lines=_json_lines(plan["lines"]),
        warnings=list(plan.get("warnings") or []),
        sub_budgets=_json_sub_budgets(plan.get("sub_budgets") or []),
        reserved_total=plan.get("reserved_total", ZERO),
    )
    return obj.save()


def plan_to_dict(obj) -> dict:
    """Stored plan -> API dict (totals recomputed from the stored lines)."""
    plan = {
        "id": obj.pk,
        "year": obj.year,
        "month": obj.month,
        "plan_type": obj.plan_type,
        "label": PLAN_LABELS.get(obj.plan_type, obj.plan_type),
        "status": obj.status,
        "reason": obj.reason,
        "currency": obj.currency,
        "income_total": Decimal(str(obj.income_total)),
        "commitments_total": Decimal(str(obj.commitments_total)),
        "lines": [dict(line) for line in (obj.lines or [])],
        "sub_budgets": [dict(sub) for sub in (getattr(obj, "sub_budgets", None) or [])],
        "warnings": list(obj.warnings or []),
        "created_at": obj.created_at.isoformat() if obj.created_at else None,
        "accepted_at": obj.accepted_at.isoformat() if obj.accepted_at else None,
    }
    return recompute_totals(plan)


def update_plan_lines(obj, amounts: dict):
    """Apply user edits {group_id: amount}; savings is recomputed from the new lines."""
    if obj.status != "suggested":
        raise ValueError("Only a suggested plan can be edited.")
    lines = [dict(line) for line in obj.lines or []]
    for line in lines:
        if line["group_id"] in amounts:
            value = Decimal(str(amounts[line["group_id"]]))
            if value < 0:
                raise ValueError("Amounts cannot be negative.")
            line["amount"] = str(money_round(value, obj.currency))
            line["basis"] = "edited"
    obj.lines = lines
    totals = recompute_totals(plan_to_dict(obj))
    obj.needs_total = totals["needs_total"]
    obj.wants_total = totals["wants_total"]
    obj.savings_amount = totals["savings_amount"]
    return obj.save()


def _activate_sub_budgets(plan: dict) -> None:
    """Accepting a plan turns the draft sub-budgets it reserves money for into active budgets."""
    from .personal_budget_constants import ACTIVE, DRAFT
    from .store import PersonalBudgetFS

    for sub in plan.get("sub_budgets") or []:
        budget = PersonalBudgetFS.get(sub.get("budget_id"))
        if budget and budget.status == DRAFT:
            budget.status = ACTIVE
            budget.save()


def accept_plan(user, obj):
    """Write the plan into the month's group budgets and savings target."""
    from django.utils import timezone

    from api.utils import trigger_budget_alerts

    from .store import SavingsFS

    if obj.status not in ("suggested", "accepted"):
        raise ValueError("This plan was replaced or dismissed; create a new one.")
    uid = _user_id(user)
    for line in obj.lines or []:
        b = BudgetFS.get_by_user_group_month(uid, str(line["group_id"]), obj.year, obj.month)
        if not b:
            b = BudgetFS(user_id=uid, group_id=str(line["group_id"]), category_id="",
                         year=obj.year, month=obj.month, forecast=ZERO)
        b.forecast = Decimal(str(line["amount"]))
        b.save()
    plan = plan_to_dict(obj)
    s = SavingsFS.get_by_user_month(uid, obj.year, obj.month) or SavingsFS(
        user_id=uid, year=obj.year, month=obj.month, target=ZERO, goal_status="pending"
    )
    s.target = max(plan["savings_amount"] + plan["invested_total"], ZERO)
    s.save()
    for other in BudgetPlanFS.list_for_month(uid, obj.year, obj.month):
        if other.pk != obj.pk and other.status in ("suggested", "accepted"):
            other.status = "superseded"
            other.save()
    _activate_sub_budgets(plan)
    obj.status = "accepted"
    obj.accepted_at = timezone.now()
    obj.save()
    trigger_budget_alerts(user, obj.year, obj.month)
    return obj
