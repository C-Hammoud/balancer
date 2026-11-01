"""
Business logic for budgeting: actuals from TransactionFS, variance, utilization reports.
"""
from decimal import Decimal
from datetime import date

from .store import (
    GroupFS,
    CategoryFS,
    TransactionFS,
    MerchantCategoryLinkFS,
    CommitmentScheduleLineFS,
    TypeCategoryMapFS,
    BudgetFS,
    BudgetThresholdFS,
)

UNMAPPED_CATEGORY_ID = "_unmapped_"
DEFAULT_WARN_PCT = Decimal("80")
DEFAULT_CRITICAL_PCT = Decimal("100")


def counts_as_income(t) -> bool:
    """Income that has settled. Pending income is not counted until it is posted."""
    return t.direction == "income" and (getattr(t, "status", "settled") or "settled") != "pending"


def counts_as_expense(t) -> bool:
    """Expenses count as spent as soon as they are recorded, pending or settled."""
    return t.direction == "expense"


def get_month_str(d):
    """Return YYYY-MM for a date."""
    return d.strftime("%Y-%m")


def _user_id(user):
    return str(user.pk) if hasattr(user, "pk") else str(user)


def _txn_amount(t, report_currency=None):
    from api.currency import convert_if_needed

    amt = t.amount or Decimal("0")
    if report_currency:
        return convert_if_needed(amt, getattr(t, "currency", None) or "USD", report_currency)
    return amt


def actual_expense_by_category(user, year, month, *, exclude_commitments: bool = False, report_currency=None):
    """
    Sum of expense amounts per category for a month from budgeting TransactionFS.
    Returns dict category_id -> total amount.
    When exclude_commitments=True, skips transactions linked to commitment installments
    so commitments do not drive budget utilization alerts.
    """
    month_str = f"{year}-{month:02d}"
    uid = _user_id(user)
    result = {}
    txns = TransactionFS.list_by_user(uid, month=month_str)
    envelopes = envelope_ids_for(user) if exclude_commitments else frozenset()
    for t in txns:
        if t.direction != "expense":
            continue
        # Utilization view: commitment installments and plan sub-budget expenses are budgeted elsewhere.
        if exclude_commitments and _expense_excluded_from_utilization(t, envelopes):
            continue
        cid = t.category_id or UNMAPPED_CATEGORY_ID
        result[cid] = result.get(cid, Decimal("0")) + _txn_amount(t, report_currency)
    return result


def actual_income_total(user, year, month, *, report_currency=None):
    """Total income for a month (exclude transfers). Firestore."""
    month_str = f"{year}-{month:02d}"
    txns = TransactionFS.list_by_user(_user_id(user), month=month_str)
    total = Decimal("0")
    for t in txns:
        if counts_as_income(t):
            total += _txn_amount(t, report_currency)
    return total


def actual_expense_total(user, year, month, *, report_currency=None):
    """Total expenses for a month from transactions."""
    by_cat = actual_expense_by_category(user, year, month, report_currency=report_currency)
    return sum(by_cat.values(), Decimal("0"))


def commitment_payments_total(user, year, month, *, report_currency=None):
    """
    Outstanding commitment installments due in the month.
    Paid installments are excluded here because they are already expense transactions.
    Each line is converted from its commitment's currency when report_currency is given.
    """
    from api.currency import convert_if_needed

    from .store import CommitmentFS

    start = date(year, month, 1)
    end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    total = Decimal("0")
    for c in CommitmentFS.list_by_user(_user_id(user)):
        currency = getattr(c, "currency", None) or "USD"
        for line in CommitmentScheduleLineFS.list_by_commitment(c.pk):
            if line.status != "outstanding" or not line.due_date:
                continue
            if start <= line.due_date < end:
                total += convert_if_needed(line.amount, currency, report_currency)
    return total


def savings_actual(user, year, month, *, report_currency=None):
    """
    Actual savings = income - expenses - outstanding commitment payments (for the month),
    all in report_currency. Without a report currency, mixed-currency amounts would be
    added together as if they were the same unit.
    """
    inc = actual_income_total(user, year, month, report_currency=report_currency)
    exp = actual_expense_total(user, year, month, report_currency=report_currency)
    comm = commitment_payments_total(user, year, month, report_currency=report_currency)
    return inc - exp - comm


def budget_variance(actual, forecast):
    """Variance = actual - forecast (positive = overspend)."""
    a = actual or Decimal("0")
    f = forecast or Decimal("0")
    return a - f


def utilization_pct(actual, forecast):
    """Utilization % = (actual / forecast) * 100 if forecast else None."""
    a = actual or Decimal("0")
    f = forecast or Decimal("0")
    if f and f != 0:
        return (a / f * 100).quantize(Decimal("0.1"))
    return None


def _build_threshold_getter(user_id):
    """Load user thresholds once; return callable(category_id) -> (warn, critical, email)."""
    thresholds = BudgetThresholdFS.list_by_user(user_id)
    by_cat = {}
    global_t = None
    for t in thresholds:
        if t.category_id:
            by_cat[t.category_id] = t
        else:
            global_t = t

    def get(category_id):
        t = by_cat.get(category_id) if category_id else global_t
        if not t and category_id:
            t = global_t
        if t:
            return t.warn_pct, t.critical_pct, t.email_enabled
        return DEFAULT_WARN_PCT, DEFAULT_CRITICAL_PCT, True

    return get


def _threshold_for(user_id, category_id):
    t = BudgetThresholdFS.get_for_category(user_id, category_id)
    if t:
        return t.warn_pct, t.critical_pct, t.email_enabled
    return DEFAULT_WARN_PCT, DEFAULT_CRITICAL_PCT, True


def _txn_month_in_year(txn, year: int):
    """Return month 1–12 if txn belongs to year, else None."""
    month_str = (txn.month or "").strip()
    if len(month_str) >= 7:
        try:
            y = int(month_str[:4])
            m = int(month_str[5:7])
            if y == year and 1 <= m <= 12:
                return m
        except ValueError:
            pass
    if txn.date and txn.date.year == year:
        return txn.date.month
    return None


def envelope_ids_for(user) -> frozenset:
    """Ids of the user's plan sub-budgets: expenses tagged to them count only in the sub-budget."""
    from .sub_budgets import envelope_ids

    try:
        return envelope_ids(user)
    except Exception:  # the budgets store being unavailable must not break the reports
        return frozenset()


def _expense_excluded_from_utilization(txn, envelope_ids: frozenset = frozenset()) -> bool:
    """
    True when the expense must not count in the regular category budgets:
    it belongs to a plan sub-budget (a trip...), or it is a commitment installment.
    """
    if envelope_ids and str(getattr(txn, "budget_id", "") or "") in envelope_ids:
        return True
    if getattr(txn, "include_in_utilization", False):
        return False
    if getattr(txn, "commitment_id", None):
        return True
    if str(getattr(txn, "external_id", "") or "").startswith("commitment_line:"):
        return True
    return False


def _budget_maps(budgets):
    """Split monthly budgets into parent (group) caps and subcategory forecasts."""
    group_budgets = {}
    cat_budgets = {}
    for b in budgets:
        if (b.category_id or "").strip():
            cat_budgets[b.category_id] = b
        elif (b.group_id or "").strip():
            group_budgets[b.group_id] = b
    return group_budgets, cat_budgets


def sub_forecast_sum(cat_budgets, subs) -> Decimal:
    """Sum of subcategory forecast amounts for a parent category."""
    total = Decimal("0")
    for cat in subs:
        b = cat_budgets.get(cat.pk)
        if b:
            total += b.forecast or Decimal("0")
    return total


def effective_group_forecast(group_budget, sub_sum: Decimal) -> Decimal:
    """
    Parent category forecast: explicit cap when set (> 0), otherwise sum of subcategory budgets.
    """
    if group_budget and (group_budget.forecast or Decimal("0")) > Decimal("0"):
        return group_budget.forecast or Decimal("0")
    return sub_sum


def _utilization_summary(actuals, budgets_for_month, categories_by_id, threshold_get, groups_list):
    """Overall utilization totals for one month (group-level forecasts, no double-counting)."""
    group_budgets, cat_budgets = _budget_maps(budgets_for_month)
    total_forecast = Decimal("0")
    total_actual = Decimal("0")

    for g in groups_list:
        subs = [
            c for c in categories_by_id.values()
            if c.group_id == g.pk and c.include_in_reports
        ]
        if not subs:
            continue
        sub_sum = sub_forecast_sum(cat_budgets, subs)
        gb = group_budgets.get(g.pk)
        effective = effective_group_forecast(gb, sub_sum)
        act = sum((actuals.get(c.pk) or Decimal("0")) for c in subs)
        if effective > 0 or act > 0:
            total_forecast += effective
            total_actual += act

    unmapped = actuals.get(UNMAPPED_CATEGORY_ID) or Decimal("0")
    if unmapped > 0:
        total_actual += unmapped

    overall_util = utilization_pct(total_actual, total_forecast)
    warn_pct, critical_pct, _ = threshold_get(None)
    overall_status = utilization_status(overall_util, warn_pct, critical_pct)

    return {
        "total_forecast": total_forecast,
        "total_actual": total_actual,
        "remaining": total_forecast - total_actual,
        "overall_util": overall_util,
        "overall_status": overall_status,
    }


def yearly_overview_report(user, year: int, *, report_currency=None):
    """
    Year-level dashboard series with one transaction load, one budget load,
    and one categories/thresholds load (instead of 36+ repeated Firestore queries).
    """
    uid = _user_id(user)
    txns = TransactionFS.list_by_user(uid, limit=2000)

    income_by_month = {m: Decimal("0") for m in range(1, 13)}
    expense_by_month = {m: Decimal("0") for m in range(1, 13)}
    util_actuals_by_month = {m: {} for m in range(1, 13)}
    envelopes = envelope_ids_for(user)

    for t in txns:
        m = _txn_month_in_year(t, year)
        if not m:
            continue
        amt = _txn_amount(t, report_currency)
        if counts_as_income(t):
            income_by_month[m] += amt
        elif t.direction == "expense":
            expense_by_month[m] += amt
            if not _expense_excluded_from_utilization(t, envelopes):
                cid = t.category_id or UNMAPPED_CATEGORY_ID
                util_actuals_by_month[m][cid] = util_actuals_by_month[m].get(cid, Decimal("0")) + amt

    groups_list, categories_by_id = categories_and_groups_for_user(user)
    threshold_get = _build_threshold_getter(uid)
    all_budgets = BudgetFS.list_by_user(uid, year=year)
    budgets_by_month = {m: [] for m in range(1, 13)}
    for b in all_budgets:
        if 1 <= b.month <= 12:
            budgets_by_month[b.month].append(b)

    months = []
    income_year = Decimal("0")
    expense_year = Decimal("0")
    for m in range(1, 13):
        income = income_by_month[m]
        expense = expense_by_month[m]
        summary = _utilization_summary(
            util_actuals_by_month[m],
            budgets_by_month[m],
            categories_by_id,
            threshold_get,
            groups_list,
        )
        income_year += income
        expense_year += expense
        months.append({
            "month": m,
            "income_total": income,
            "expense_total": expense,
            "net": income - expense,
            **summary,
        })

    return {
        "year": year,
        "report_currency": report_currency or "USD",
        "income_total": income_year,
        "expense_total": expense_year,
        "net": income_year - expense_year,
        "months": months,
    }


def utilization_status(util, warn_pct, critical_pct):
    """Return ok|warn|critical|over based on utilization % and thresholds."""
    if util is None:
        return "ok"
    if util > critical_pct:
        return "over"
    if util >= critical_pct:
        return "critical"
    if util >= warn_pct:
        return "warn"
    return "ok"


def budget_utilization_report(user, year, month, *, report_currency=None):
    """
    Per-category utilization report for a month.
    Parent category rows use an explicit cap when set, otherwise the sum of subcategory forecasts.
    Subcategory rows are included for detail and do not double-count in totals.
    """
    uid = _user_id(user)
    groups_list, categories_by_id = categories_and_groups_for_user(user)
    groups_map = {g.pk: g for g in groups_list}
    budgets = BudgetFS.list_by_user(uid, year=year, month=month)
    group_budgets, cat_budgets = _budget_maps(budgets)
    actuals = actual_expense_by_category(
        user, year, month, exclude_commitments=True, report_currency=report_currency
    )

    rows = []

    for g in sorted(groups_list, key=lambda x: (x.order, x.name.lower())):
        subs = [
            c for c in categories_by_id.values()
            if c.group_id == g.pk and c.include_in_reports
        ]
        if not subs:
            continue
        sub_sum = sub_forecast_sum(cat_budgets, subs)
        gb = group_budgets.get(g.pk)
        effective = effective_group_forecast(gb, sub_sum)
        group_actual = sum((actuals.get(c.pk) or Decimal("0")) for c in subs)
        has_sub_budgets = any(cat.pk in cat_budgets for cat in subs)
        if effective <= 0 and group_actual <= 0 and not gb and not has_sub_budgets:
            continue

        util = utilization_pct(group_actual, effective)
        warn_pct, critical_pct, email_enabled = _threshold_for(uid, None)
        status = utilization_status(util, warn_pct, critical_pct)
        rows.append({
            "category_id": f"group:{g.pk}",
            "category_name": g.name,
            "group_name": g.name,
            "forecast": effective,
            "forecast_explicit": (gb.forecast if gb and (gb.forecast or Decimal("0")) > Decimal("0") else None),
            "forecast_from_subs": sub_sum,
            "actual": group_actual,
            "remaining": effective - group_actual,
            "variance": budget_variance(group_actual, effective),
            "utilization_pct": util,
            "status": status,
            "warn_pct": warn_pct,
            "critical_pct": critical_pct,
            "email_enabled": email_enabled,
            "include_in_total": True,
            "row_type": "group",
        })

        for cat in sorted(subs, key=lambda c: (c.order, c.name.lower())):
            sub_forecast = (cat_budgets[cat.pk].forecast if cat.pk in cat_budgets else Decimal("0")) or Decimal("0")
            sub_act = actuals.get(cat.pk) or Decimal("0")
            if sub_forecast <= 0 and sub_act <= 0:
                continue
            group_name = groups_map.get(cat.group_id).name if cat.group_id in groups_map else ""
            sub_util = utilization_pct(sub_act, sub_forecast)
            sw, sc, se = _threshold_for(uid, cat.pk)
            rows.append({
                "category_id": cat.pk,
                "category_name": cat.name,
                "group_name": group_name,
                "forecast": sub_forecast,
                "actual": sub_act,
                "remaining": sub_forecast - sub_act,
                "variance": budget_variance(sub_act, sub_forecast),
                "utilization_pct": sub_util,
                "status": utilization_status(sub_util, sw, sc),
                "warn_pct": sw,
                "critical_pct": sc,
                "email_enabled": se,
                "include_in_total": False,
                "row_type": "subcategory",
                "parent_group_id": g.pk,
            })

    unmapped = actuals.get(UNMAPPED_CATEGORY_ID) or Decimal("0")
    if unmapped > 0:
        rows.append({
            "category_id": UNMAPPED_CATEGORY_ID,
            "category_name": "Unmapped expenses",
            "group_name": "Other",
            "forecast": Decimal("0"),
            "actual": unmapped,
            "remaining": -unmapped,
            "variance": unmapped,
            "utilization_pct": None,
            "status": "warn",
            "warn_pct": DEFAULT_WARN_PCT,
            "critical_pct": DEFAULT_CRITICAL_PCT,
            "email_enabled": True,
            "include_in_total": True,
            "row_type": "unmapped",
        })

    total_forecast = sum(
        (r["forecast"] for r in rows if r.get("include_in_total", True)),
        Decimal("0"),
    )
    total_actual = sum((r["actual"] for r in rows if r.get("include_in_total", True)), Decimal("0"))
    overall_util = utilization_pct(total_actual, total_forecast)
    warn_pct, critical_pct, _ = _threshold_for(uid, None)
    overall_status = utilization_status(overall_util, warn_pct, critical_pct)

    return {
        "report_currency": report_currency or "USD",
        "rows": rows,
        "total_forecast": total_forecast,
        "total_actual": total_actual,
        "overall_variance": budget_variance(total_actual, total_forecast),
        "overall_util": overall_util,
        "overall_status": overall_status,
        "remaining": total_forecast - total_actual,
    }


def suggest_category_for_description(description, user=None):
    """
    Suggest category from MerchantCategoryLink (Firestore) by keyword match (case-insensitive).
    Prefers the longest matching keyword (most specific). User links override globals.
    Returns CategoryFS or None.
    """
    if not description:
        return None
    desc_lower = description.lower()
    uid = _user_id(user) if user else None

    def _best_from(links):
        best_link = None
        best_len = 0
        for link in links:
            kw = (link.keyword or "").strip().lower()
            if not kw:
                continue
            if kw in desc_lower and len(kw) > best_len:
                best_link = link
                best_len = len(kw)
        if best_link:
            return CategoryFS.get(best_link.category_id)
        return None

    if uid:
        cat = _best_from(MerchantCategoryLinkFS.list_by_user(uid))
        if cat:
            return cat
    global_links = [l for l in MerchantCategoryLinkFS.list_all(limit=1000) if not l.user_id]
    return _best_from(global_links)


def merchant_key_from_description(description: str) -> str:
    """Normalize a CSV description into a merchant label for unmatched grouping."""
    if not description:
        return ""
    text = " ".join(str(description).split()).strip()
    return text[:120]


def _assign_merchant_category(t, category_id: str) -> None:
    """Set subcategory and keep the original bank description in note."""
    cat = CategoryFS.get(category_id)
    merchant_name = (cat.name if cat else "").strip()
    original = (t.description or "").strip()
    if original and merchant_name and original.lower() != merchant_name.lower():
        existing = (t.note or "").strip()
        if not existing:
            t.note = original
        elif original not in existing:
            t.note = f"{original} · {existing}"
        t.description = merchant_name[:500]
    t.category_id = category_id


def apply_merchant_link_to_transactions(user, keyword: str, category_id: str, transaction_ids=None):
    """
    Set category_id on user's expense transactions that match the keyword
    (or are in transaction_ids). Returns number updated.
    """
    uid = _user_id(user)
    kw = (keyword or "").strip().lower()
    if not kw and not transaction_ids:
        return 0
    id_set = set(transaction_ids or [])
    updated = 0
    # Prefer explicit ids from the import batch; also scan recent txns if needed
    candidates = []
    if id_set:
        for tid in id_set:
            t = TransactionFS.get(tid)
            if t and t.user_id == uid:
                candidates.append(t)
    else:
        candidates = TransactionFS.list_by_user(uid, limit=500)

    for t in candidates:
        if t.direction != "expense":
            continue
        desc = (t.description or "").lower()
        if id_set and t.pk in id_set:
            _assign_merchant_category(t, category_id)
            t.save()
            updated += 1
            continue
        if kw and kw in desc and not t.category_id:
            _assign_merchant_category(t, category_id)
            t.save()
            updated += 1
    return updated


def remaining_principal(commitment_fs):
    """Sum of outstanding schedule line amounts for a CommitmentFS."""
    return CommitmentScheduleLineFS.sum_outstanding_by_commitment(commitment_fs.pk)


def categories_and_groups_for_user(user=None):
    """
    Return (groups_list, categories_by_id) visible to `user`: shared defaults plus their own.
    user=None returns every group/category (admin and batch use only).
    categories_by_id[category_id] = CategoryFS (with group_id); resolve group name from groups.
    """
    if user is None:
        groups = {g.pk: g for g in GroupFS.list_all(limit=2000)}
        categories = CategoryFS.list_all(limit=5000)
    else:
        from .category_access import visible_categories, visible_groups

        groups = {g.pk: g for g in visible_groups(user)}
        categories = visible_categories(user)
    by_id = {c.pk: c for c in categories}
    for c in by_id.values():
        c.group_name = groups.get(c.group_id).name if c.group_id and c.group_id in groups else ""
    return list(groups.values()), by_id
