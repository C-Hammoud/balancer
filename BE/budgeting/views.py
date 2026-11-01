"""
Budgeting app views: dashboard, transactions, budget, savings, commitments, financial standing, config.
All data is read from and written to Firestore (Firebase); no Django ORM for budgeting data.
"""
from django.shortcuts import render, redirect
from django.urls import reverse
from django.http import Http404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.paginator import Paginator
from decimal import Decimal
from datetime import date, datetime
import csv
import io
import json

from .store import (
    GroupFS,
    CategoryFS,
    TransactionFS,
    BudgetFS,
    SavingsFS,
    CommitmentFS,
    CommitmentScheduleLineFS,
    FinancialStandingFS,
    MerchantCategoryLinkFS,
    TypeCategoryMapFS,
    BudgetThresholdFS,
    BudgetAlertFS,
    CONSUMPTION_TYPES,
)
from .forms_firestore import (
    TransactionFormFS,
    BudgetEditFormFS,
    SavingsFormFS,
    CommitmentFormFS,
    FinancialStandingFormFS,
    MerchantCategoryLinkFormFS,
    TransactionUploadForm,
    TypeCategoryMapFormFS,
    BudgetThresholdFormFS,
)
from .models import Direction, GoalStatus
from .services import (
    get_month_str,
    actual_expense_by_category,
    actual_expense_total,
    actual_income_total,
    savings_actual,
    budget_variance,
    utilization_pct,
    suggest_category_for_description,
    remaining_principal,
    categories_and_groups_for_user,
    budget_utilization_report,
    CONSUMPTION_EXTERNAL_ID_PREFIX,
)
from .alerts import evaluate_budget_alerts, resolve_alert


def _category_display(cat_fs, group_name):
    """Simple namespace so template can use category.name and category.group.name."""
    class G:
        name = group_name
    class C:
        id = cat_fs.pk
        name = cat_fs.name
        group = G
        include_in_reports = cat_fs.include_in_reports
    return C()


def _trigger_alert_eval(user, year=None, month=None):
    """Best-effort alert evaluation; never raises to the caller."""
    try:
        evaluate_budget_alerts(user, year=year, month=month)
    except Exception:
        pass


@login_required
def dashboard(request):
    """Monthly budget dashboard: budget vs actual by category (Firestore), incl. expense consumptions."""
    today = date.today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))
    month_str = f"{year}-{month:02d}"

    report = budget_utilization_report(request.user, year, month)
    _trigger_alert_eval(request.user, year, month)

    rows = []
    for r in report["rows"]:
        class G:
            name = r["group_name"]
        class C:
            id = r["category_id"]
            name = r["category_name"]
            group = G
        rows.append({
            "category": C(),
            "forecast": r["forecast"],
            "actual": r["actual"],
            "remaining": r["remaining"],
            "variance": r["variance"],
            "utilization_pct": r["utilization_pct"],
            "status": r["status"],
            "warn_pct": r["warn_pct"],
            "critical_pct": r["critical_pct"],
        })

    highest = max(rows, key=lambda r: r["actual"]) if rows else None
    overspends = sorted([r for r in rows if r["variance"] > 0], key=lambda r: r["variance"], reverse=True)[:5]
    open_alerts = BudgetAlertFS.list_for_month(str(request.user.pk), year, month, open_only=True)
    income_total = actual_income_total(request.user, year, month)
    expense_total = actual_expense_total(request.user, year, month)

    context = {
        "year": year,
        "month": month,
        "month_str": month_str,
        "years": list(range(today.year - 2, today.year + 3)),
        "rows": rows,
        "total_forecast": report["total_forecast"],
        "total_actual": report["total_actual"],
        "overall_variance": report["overall_variance"],
        "overall_util": report["overall_util"],
        "overall_status": report["overall_status"],
        "remaining_budget": report["remaining"],
        "highest": highest,
        "top_overspends": overspends,
        "income_total": income_total,
        "expense_total": expense_total,
        "open_alerts": open_alerts,
    }
    return render(request, "budgeting/dashboard.html", context)


@login_required
def transaction_list(request):
    """List transactions from Firestore with optional month filter. Supports expenses inquiry in a modal."""
    month_str = request.GET.get("month")
    inquiry_month = request.GET.get("inquiry_month")
    uid = str(request.user.pk)
    txns = TransactionFS.list_by_user(uid, month=month_str)
    _, categories_by_id = categories_and_groups_for_user()
    # Paginate in memory
    paginator = Paginator(txns, 50)
    page = request.GET.get("page", 1)
    transactions = paginator.get_page(page)
    # Attach category name and direction display for template
    direction_labels = dict(Direction.choices)
    for t in transactions.object_list:
        t.category_name = categories_by_id.get(t.category_id).name if t.category_id and t.category_id in categories_by_id else "—"
        t.direction_display = direction_labels.get(t.direction, t.direction)
    # Expenses inquiry: available months from consumptions only
    inquiry_available_months, inquiry_years, inquiry_year_months = _inquiry_available_months(uid)
    context = {
        "transactions": transactions,
        "month_filter": month_str,
        "inquiry_available_months": inquiry_available_months,
        "inquiry_years": inquiry_years,
        "inquiry_year_months": inquiry_year_months,
        "inquiry_year_months_json": json.dumps(inquiry_year_months),
        "open_inquiry_modal": False,
        "inquiry_month": None,
        "inquiry_merged_list": [],
    }
    if inquiry_month and len(inquiry_month) == 7 and inquiry_month[4] == "-":
        try:
            int(inquiry_month[:4])
            int(inquiry_month[5:7])
            context["open_inquiry_modal"] = True
            context["inquiry_month"] = inquiry_month
            added_ids = _consumption_ids_already_added(uid, inquiry_month)
            txns_month = TransactionFS.list_by_user(uid, inquiry_month)
            consumption_to_txn_pk = {}
            for t in txns_month:
                eid = getattr(t, "external_id", None) or ""
                if eid.startswith(CONSUMPTION_EXTERNAL_ID_PREFIX):
                    consumption_to_txn_pk[eid[len(CONSUMPTION_EXTERNAL_ID_PREFIX) :].strip()] = t.pk
            context["inquiry_merged_list"] = _merged_consumption_and_transactions(
                uid, inquiry_month, categories_by_id,
                added_consumption_ids=added_ids,
                consumption_to_txn_pk=consumption_to_txn_pk,
            )
        except ValueError:
            pass
    return render(request, "budgeting/transaction_list.html", context)


def _inquiry_available_months(uid):
    """Return distinct (year, month) from consumptions for this user. Values: list of 'YYYY-MM', and year_months dict {year: [month, ...]}."""
    try:
        from expenses.store import ConsumptionFS
        consumptions = ConsumptionFS.query_by_field("created_by", "==", uid)
        seen = set()
        for c in consumptions:
            if c.date and (c.record_status or "active") == "active":
                key = (c.date.year, c.date.month)
                if key not in seen:
                    seen.add(key)
        # Build sorted list of YYYY-MM (newest first)
        sorted_keys = sorted(seen, reverse=True)
        available_months = [f"{y}-{m:02d}" for y, m in sorted_keys]
        years = sorted({y for y, m in seen}, reverse=True)
        year_months = {}
        for y, m in seen:
            year_months.setdefault(y, []).append(f"{m:02d}")
        for y in year_months:
            year_months[y].sort(reverse=True)
        return available_months, years, year_months
    except Exception:
        return [], [], {}


def _consumption_ids_already_added(uid, month_str):
    """Return set of consumption Firestore doc IDs that already have a transaction (external_id = consumption:pk)."""
    txns = TransactionFS.list_by_user(uid, month=month_str)
    added = set()
    for t in txns:
        eid = getattr(t, "external_id", None) or ""
        if eid.startswith(CONSUMPTION_EXTERNAL_ID_PREFIX):
            added.add(eid[len(CONSUMPTION_EXTERNAL_ID_PREFIX) :].strip())
    return added


def _merged_consumption_and_transactions(uid, month_str, categories_by_id, added_consumption_ids=None, consumption_to_txn_pk=None):
    """Build a single list of consumption (expenses app) + expense transactions (budgeting) for the given month, sorted by date. For Consumption rows includes consumption_pk, already_added, and transaction_pk (if added)."""
    from datetime import date as date_type
    added = added_consumption_ids or set()
    txn_pk_map = consumption_to_txn_pk or {}
    year, month = int(month_str[:4]), int(month_str[5:7])
    start = date_type(year, month, 1)
    if month == 12:
        end = date_type(year + 1, 1, 1)
    else:
        end = date_type(year, month + 1, 1)
    merged = []
    try:
        from expenses.store import ConsumptionFS
        consumptions = ConsumptionFS.query_by_field("created_by", "==", uid)
        for c in consumptions:
            if c.date and start <= c.date < end and (c.record_status or "active") == "active":
                merged.append({
                    "date": c.date,
                    "source": "Consumption",
                    "description": c.note or "—",
                    "type_category": c.consumption_type or "—",
                    "amount": c.amount,
                    "currency": c.currency or "USD",
                    "consumption_pk": c.pk,
                    "already_added": c.pk in added,
                    "transaction_pk": txn_pk_map.get(c.pk),
                })
    except Exception:
        pass
    txns = TransactionFS.list_by_user(uid, month=month_str)
    for t in txns:
        if t.direction != "expense":
            continue
        c = categories_by_id.get(t.category_id) if t.category_id else None
        cat_name = c.name if c else "—"
        merged.append({
            "date": t.date,
            "source": "Transaction",
            "description": (t.description or "—")[:80],
            "type_category": cat_name,
            "amount": t.amount,
            "currency": "SAR",
            "consumption_pk": None,
            "already_added": False,
            "transaction_pk": None,
        })
    merged.sort(key=lambda x: (x["date"] or date_type(1970, 1, 1)))
    return merged


@login_required
def transaction_expenses_inquiry(request):
    """List only expense transactions for the user (inquire expenses) with optional month filter and total."""
    month_str = request.GET.get("month")
    uid = str(request.user.pk)
    txns = TransactionFS.list_by_user(uid, month=month_str)
    expenses_only = [t for t in txns if t.direction == "expense"]
    total_expenses = sum((t.amount for t in expenses_only), Decimal("0"))
    _, categories_by_id = categories_and_groups_for_user()
    direction_labels = dict(Direction.choices)
    for t in expenses_only:
        t.category_name = categories_by_id.get(t.category_id).name if t.category_id and t.category_id in categories_by_id else "—"
        t.direction_display = direction_labels.get(t.direction, t.direction)
    paginator = Paginator(expenses_only, 50)
    page = request.GET.get("page", 1)
    transactions = paginator.get_page(page)
    merged_list = []
    if month_str:
        merged_list = _merged_consumption_and_transactions(uid, month_str, categories_by_id)
    return render(
        request,
        "budgeting/transaction_expenses_inquiry.html",
        {
            "transactions": transactions,
            "month_filter": month_str,
            "total_expenses": total_expenses,
            "merged_list": merged_list,
        },
    )


@login_required
def consumption_add_to_transaction(request):
    """Create one budgeting transaction from an expenses-app consumption. POST only; redirects back to transaction list with inquiry modal."""
    if request.method != "POST":
        return redirect("budgeting:transaction_list")
    consumption_id = (request.POST.get("consumption_id") or "").strip()
    inquiry_month = (request.GET.get("next_month") or request.POST.get("next_month") or "").strip()
    if not consumption_id:
        messages.error(request, "No consumption selected.")
        _url = reverse("budgeting:transaction_list")
        if inquiry_month:
            _url += "?inquiry_month=" + inquiry_month
        return redirect(_url)
    uid = str(request.user.pk)
    try:
        from expenses.store import ConsumptionFS
        c = ConsumptionFS.get(consumption_id)
    except Exception:
        c = None
    if not c or c.created_by != uid:
        messages.error(request, "Consumption not found or access denied.")
        _url = reverse("budgeting:transaction_list")
        if inquiry_month:
            _url += "?inquiry_month=" + inquiry_month
        return redirect(_url)
    ext_id = CONSUMPTION_EXTERNAL_ID_PREFIX + consumption_id
    if TransactionFS.exists_by_external_id(uid, ext_id):
        messages.info(request, "This consumption is already in your transactions.")
        _url = reverse("budgeting:transaction_list")
        if inquiry_month:
            _url += "?inquiry_month=" + inquiry_month
        return redirect(_url)
    t = TransactionFS(
        user_id=uid,
        date=c.date,
        month=get_month_str(c.date) if c.date else "",
        description=(c.note or "From expense")[:500],
        category_id=None,
        classification=None,
        amount=c.amount,
        direction="expense",
        source_account="",
        external_id=ext_id,
    )
    if c.note:
        suggested = suggest_category_for_description(c.note, request.user)
        if suggested:
            t.category_id = suggested.pk
    t.save()
    messages.success(request, "Expense added to transactions. You can edit it to set category.")
    _url = reverse("budgeting:transaction_list")
    if inquiry_month:
        _url += "?inquiry_month=" + inquiry_month
    return redirect(_url)


@login_required
def consumption_add_all_to_transactions(request):
    """Create budgeting transactions for all consumptions in the given month that are not already added. POST only."""
    if request.method != "POST":
        return redirect("budgeting:transaction_list")
    inquiry_month = (request.POST.get("inquiry_month") or request.GET.get("inquiry_month") or "").strip()
    if len(inquiry_month) != 7 or inquiry_month[4] != "-":
        messages.error(request, "Invalid month.")
        return redirect("budgeting:transaction_list")
    uid = str(request.user.pk)
    try:
        int(inquiry_month[:4])
        int(inquiry_month[5:7])
    except ValueError:
        messages.error(request, "Invalid month.")
        return redirect("budgeting:transaction_list")
    added_ids = _consumption_ids_already_added(uid, inquiry_month)
    try:
        from expenses.store import ConsumptionFS
        consumptions = ConsumptionFS.query_by_field("created_by", "==", uid)
    except Exception:
        consumptions = []
    from datetime import date as date_type
    year, month = int(inquiry_month[:4]), int(inquiry_month[5:7])
    start = date_type(year, month, 1)
    end = date_type(year, month + 1, 1) if month < 12 else date_type(year + 1, 1, 1)
    created = 0
    for c in consumptions:
        if not c.date or not (start <= c.date < end) or (c.record_status or "active") != "active":
            continue
        if c.pk in added_ids:
            continue
        ext_id = CONSUMPTION_EXTERNAL_ID_PREFIX + c.pk
        if TransactionFS.exists_by_external_id(uid, ext_id):
            added_ids.add(c.pk)
            continue
        t = TransactionFS(
            user_id=uid,
            date=c.date,
            month=get_month_str(c.date),
            description=(c.note or "From expense")[:500],
            category_id=None,
            classification=None,
            amount=c.amount,
            direction="expense",
            source_account="",
            external_id=ext_id,
        )
        if c.note:
            suggested = suggest_category_for_description(c.note, request.user)
            if suggested:
                t.category_id = suggested.pk
        t.save()
        created += 1
        added_ids.add(c.pk)
    if created:
        messages.success(request, f"Added {created} expense(s) to transactions. You can edit them to set categories.")
    else:
        messages.info(request, "No new consumptions to add; they are already in your transactions.")
    return redirect(reverse("budgeting:transaction_list") + "?inquiry_month=" + inquiry_month)


def _transaction_form_choices():
    groups = GroupFS.list_all()
    categories = CategoryFS.list_all()
    gmap = {g.pk: g for g in groups}
    return [("", "—")] + [(c.pk, f"{gmap.get(c.group_id).name if c.group_id in gmap else ''} — {c.name}") for c in categories]


@login_required
def transaction_add(request):
    """Add a single transaction to Firestore."""
    choices = _transaction_form_choices()
    if request.method == "POST":
        form = TransactionFormFS(request.POST, category_choices=choices)
        if form.is_valid():
            cd = form.cleaned_data
            t = TransactionFS(
                user_id=str(request.user.pk),
                date=cd["date"],
                month=get_month_str(cd["date"]),
                description=cd["description"],
                category_id=cd.get("category_id") or None,
                classification=cd.get("classification") or None,
                amount=cd["amount"],
                direction=cd["direction"],
                source_account=cd.get("source_account") or "",
            )
            if not t.category_id and cd.get("description"):
                suggested = suggest_category_for_description(cd["description"], request.user)
                if suggested:
                    t.category_id = suggested.pk
            t.save()
            messages.success(request, "Transaction added.")
            _trigger_alert_eval(request.user, year=t.date.year if t.date else None, month=t.date.month if t.date else None)
            return redirect("budgeting:transaction_list")
    else:
        form = TransactionFormFS(category_choices=choices)
    return render(request, "budgeting/transaction_form.html", {"form": form, "title": "Add transaction"})


@login_required
def transaction_edit(request, pk):
    """Edit a transaction in Firestore."""
    t = TransactionFS.get(pk)
    if not t or t.user_id != str(request.user.pk):
        raise Http404("Transaction not found")
    choices = _transaction_form_choices()
    if request.method == "POST":
        form = TransactionFormFS(request.POST, category_choices=choices)
        if form.is_valid():
            cd = form.cleaned_data
            t.date = cd["date"]
            t.month = get_month_str(cd["date"])
            t.description = cd["description"]
            t.category_id = cd.get("category_id") or None
            t.classification = cd.get("classification") or None
            t.amount = cd["amount"]
            t.direction = cd["direction"]
            t.source_account = cd.get("source_account") or ""
            t.save()
            messages.success(request, "Transaction updated.")
            _trigger_alert_eval(request.user, year=t.date.year if t.date else None, month=t.date.month if t.date else None)
            return redirect("budgeting:transaction_list")
    else:
        form = TransactionFormFS(category_choices=choices, initial={
            "date": t.date,
            "description": t.description,
            "category_id": t.category_id or "",
            "classification": t.classification or "",
            "amount": t.amount,
            "direction": t.direction,
            "source_account": t.source_account or "",
        })
    return render(request, "budgeting/transaction_form.html", {"form": form, "title": "Edit transaction", "transaction": t})


@login_required
def transaction_upload(request):
    """Upload CSV and import transactions into Firestore with dedup."""
    if request.method != "POST":
        form = TransactionUploadForm()
        return render(request, "budgeting/transaction_upload.html", {"form": form})

    form = TransactionUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "budgeting/transaction_upload.html", {"form": form})

    f = request.FILES["file"]
    if not f.name.lower().endswith(".csv"):
        messages.error(request, "Only CSV is supported. Save Excel as CSV first.")
        return redirect("budgeting:transaction_upload")

    try:
        content = f.read().decode("utf-8-sig")
    except Exception:
        content = f.read().decode("latin-1")
    reader = csv.reader(io.StringIO(content))
    rows = list(reader)
    if not rows:
        messages.error(request, "File is empty.")
        return redirect("budgeting:transaction_upload")

    uid = str(request.user.pk)
    created = 0
    skipped = 0
    for row in rows[1:]:
        if len(row) < 3:
            continue
        try:
            dt = datetime.strptime(row[0].strip()[:10], "%Y-%m-%d")
        except Exception:
            try:
                dt = datetime.strptime(row[0].strip()[:10], "%d/%m/%Y")
            except Exception:
                skipped += 1
                continue
        desc = (row[1] if len(row) > 1 else "").strip()[:500]
        try:
            amt = Decimal(row[2].replace(",", "").strip())
        except Exception:
            skipped += 1
            continue
        direction = "expense" if amt < 0 else "income"
        amount = abs(amt)
        month_str = get_month_str(dt.date())
        ext_id = f"{dt.date()}-{amount}-{desc[:50]}"
        if TransactionFS.exists_by_external_id(uid, ext_id):
            skipped += 1
            continue
        cat = suggest_category_for_description(desc, request.user)
        t = TransactionFS(
            user_id=uid,
            date=dt.date(),
            month=month_str,
            description=desc,
            amount=amount,
            direction=direction,
            category_id=cat.pk if cat else None,
            external_id=ext_id,
        )
        t.save()
        created += 1

    messages.success(request, f"Imported {created} transactions to Firebase, skipped {skipped}.")
    _trigger_alert_eval(request.user)
    return redirect("budgeting:transaction_list")


@login_required
def budget_add(request):
    """Choose year, month, and category; redirect to budget_edit to set forecast."""
    today = date.today()
    years = list(range(today.year - 2, today.year + 4))
    _, categories_by_id = categories_and_groups_for_user()
    groups_map = {g.pk: g for g in GroupFS.list_all()}
    category_choices = [("", "— Select category —")]
    for c in categories_by_id.values():
        gname = groups_map.get(c.group_id).name if c.group_id in groups_map else ""
        category_choices.append((c.pk, f"{gname} — {c.name}" if gname else c.name))
    if request.method == "POST":
        y = request.POST.get("year")
        m = request.POST.get("month")
        cid = request.POST.get("category_id")
        try:
            year = int(y)
            month = int(m)
        except (TypeError, ValueError):
            messages.error(request, "Please select a valid year and month.")
            return render(
                request,
                "budgeting/budget_add.html",
                {"years": years, "category_choices": category_choices, "year": None, "month": None},
            )
        if month < 1 or month > 12:
            messages.error(request, "Month must be 1–12.")
            return render(
                request,
                "budgeting/budget_add.html",
                {"years": years, "category_choices": category_choices, "year": year, "month": month},
            )
        if not cid or cid not in categories_by_id:
            messages.error(request, "Please select a category.")
            return render(
                request,
                "budgeting/budget_add.html",
                {"years": years, "category_choices": category_choices, "year": year, "month": month},
            )
        return redirect("budgeting:budget_edit", year=year, month=month, category_id=cid)
    year = None
    month = None
    if request.GET.get("year"):
        try:
            year = int(request.GET.get("year"))
        except ValueError:
            pass
    if request.GET.get("month"):
        try:
            month = int(request.GET.get("month"))
            if month < 1 or month > 12:
                month = None
        except ValueError:
            month = None
    return render(
        request,
        "budgeting/budget_add.html",
        {"years": years, "category_choices": category_choices, "year": year, "month": month},
    )


def _prev_month(year, month):
    if month == 1:
        return year - 1, 12
    return year, month - 1


def _next_month(year, month):
    if month == 12:
        return year + 1, 1
    return year, month + 1


MONTH_NAMES = [
    "", "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


@login_required
def budget_list(request):
    """Single-month budget view: navigator card (prev/next month) and grid of category vs forecast vs actual."""
    uid = str(request.user.pk)
    today = date.today()
    try:
        year = int(request.GET.get("year", today.year))
    except (TypeError, ValueError):
        year = today.year
    try:
        month = int(request.GET.get("month", today.month))
    except (TypeError, ValueError):
        month = today.month
    if month < 1 or month > 12:
        month = today.month
    prev_year, prev_month = _prev_month(year, month)
    next_year, next_month = _next_month(year, month)
    month_label = f"{MONTH_NAMES[month]} {year}"

    groups_list, categories_by_id = categories_and_groups_for_user()
    groups_map = {g.pk: g for g in groups_list}
    budgets = BudgetFS.list_by_user(uid, year=year, month=month)
    actuals = actual_expense_by_category(request.user, year, month)

    rows = []
    for b in budgets:
        cat_fs = categories_by_id.get(b.category_id)
        if not cat_fs or not cat_fs.include_in_reports:
            continue
        group_name = groups_map.get(cat_fs.group_id).name if cat_fs.group_id in groups_map else ""
        cat_display = _category_display(cat_fs, group_name)
        act = actuals.get(b.category_id) or Decimal("0")
        rows.append({
            "category": cat_display,
            "category_id": b.category_id,
            "forecast": b.forecast,
            "actual": act,
        })
    for cat_id, act in actuals.items():
        if cat_id == "_none_" or any(r["category_id"] == cat_id for r in rows):
            continue
        cat_fs = categories_by_id.get(cat_id)
        if not cat_fs or not cat_fs.include_in_reports:
            continue
        group_name = groups_map.get(cat_fs.group_id).name if cat_fs.group_id in groups_map else ""
        rows.append({
            "category": _category_display(cat_fs, group_name),
            "category_id": cat_id,
            "forecast": Decimal("0"),
            "actual": act,
        })

    return render(
        request,
        "budgeting/budget_list.html",
        {
            "year": year,
            "month": month,
            "month_label": month_label,
            "prev_year": prev_year,
            "prev_month": prev_month,
            "next_year": next_year,
            "next_month": next_month,
            "rows": rows,
        },
    )


@login_required
def budget_edit(request, year, month, category_id):
    """Create or edit budget in Firestore for category/month."""
    year, month = int(year), int(month)
    uid = str(request.user.pk)
    cat = CategoryFS.get(str(category_id))
    if not cat:
        raise Http404("Category not found")
    cid = str(category_id)
    budget = BudgetFS.get_by_user_category_month(uid, cid, year, month)
    if not budget:
        budget = BudgetFS(user_id=uid, category_id=cid, year=year, month=month, forecast=Decimal("0"))
        budget.save()
    groups_map = {g.pk: g for g in GroupFS.list_all()}
    group_name = groups_map.get(cat.group_id).name if cat.group_id in groups_map else ""

    if request.method == "POST":
        form = BudgetEditFormFS(request.POST)
        if form.is_valid():
            budget.forecast = form.cleaned_data["forecast"]
            budget.save()
            messages.success(request, "Budget updated.")
            _trigger_alert_eval(request.user, year=year, month=month)
            return redirect(reverse("budgeting:budget_list") + "?year=%d&month=%d" % (year, month))
    else:
        form = BudgetEditFormFS(initial={"forecast": budget.forecast})
    return render(request, "budgeting/budget_form.html", {"form": form, "budget": budget, "category": cat, "group_name": group_name, "year": year, "month": month})


@login_required
def savings_list(request):
    """List savings from Firestore; compute actual from transactions if not set."""
    uid = str(request.user.pk)
    savings_list_data = SavingsFS.list_by_user(uid)
    goal_labels = dict(GoalStatus.choices)
    for s in savings_list_data:
        if s.actual is None:
            s.actual = savings_actual(request.user, s.year, s.month)
        s.goal_status_display = goal_labels.get(s.goal_status, s.goal_status)
    return render(request, "budgeting/savings_list.html", {"savings_list": savings_list_data})


@login_required
def savings_edit(request, year, month):
    """Edit savings target/actual/status in Firestore."""
    year, month = int(year), int(month)
    uid = str(request.user.pk)
    obj = SavingsFS.get_by_user_month(uid, year, month)
    if not obj:
        obj = SavingsFS(user_id=uid, year=year, month=month, target=Decimal("0"), goal_status="pending")
        obj.save()
    if request.method == "POST":
        form = SavingsFormFS(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            obj.target = cd["target"]
            obj.actual = cd.get("actual")
            obj.goal_status = cd["goal_status"]
            obj.save()
            messages.success(request, "Savings updated.")
            return redirect("budgeting:savings_list")
    else:
        form = SavingsFormFS(initial={"year": obj.year, "month": obj.month, "target": obj.target, "actual": obj.actual, "goal_status": obj.goal_status})
    return render(request, "budgeting/savings_form.html", {"form": form, "savings": obj})


@login_required
def commitment_list(request):
    """List commitments from Firestore with remaining balance."""
    uid = str(request.user.pk)
    commitments = CommitmentFS.list_by_user(uid)
    for c in commitments:
        c.remaining = remaining_principal(c)
    return render(request, "budgeting/commitment_list.html", {"commitments": commitments})


@login_required
def commitment_add(request):
    if request.method == "POST":
        form = CommitmentFormFS(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            c = CommitmentFS(
                user_id=str(request.user.pk),
                name=cd["name"],
                amount=cd["amount"],
                start_date=cd["start_date"],
                term_months=cd["term_months"],
                frequency=cd["frequency"],
                payment_amount=cd["payment_amount"],
                balloon=cd.get("balloon") or Decimal("0"),
            )
            c.save()
            messages.success(request, "Commitment added. Add schedule lines in Firebase console or later.")
            return redirect("budgeting:commitment_list")
    else:
        form = CommitmentFormFS()
    return render(request, "budgeting/commitment_form.html", {"form": form, "title": "Add commitment"})


@login_required
def commitment_edit(request, pk):
    c = CommitmentFS.get(pk)
    if not c or c.user_id != str(request.user.pk):
        raise Http404("Commitment not found")
    if request.method == "POST":
        form = CommitmentFormFS(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            c.name = cd["name"]
            c.amount = cd["amount"]
            c.start_date = cd["start_date"]
            c.term_months = cd["term_months"]
            c.frequency = cd["frequency"]
            c.payment_amount = cd["payment_amount"]
            c.balloon = cd.get("balloon") or Decimal("0")
            c.save()
            messages.success(request, "Commitment updated.")
            return redirect("budgeting:commitment_list")
    else:
        form = CommitmentFormFS(initial={
            "name": c.name,
            "amount": c.amount,
            "start_date": c.start_date,
            "term_months": c.term_months,
            "frequency": c.frequency,
            "payment_amount": c.payment_amount,
            "balloon": c.balloon,
        })
    return render(request, "budgeting/commitment_form.html", {"form": form, "title": "Edit commitment", "commitment": c})


@login_required
def financial_standing_list(request):
    """List financial standing snapshots from Firestore."""
    uid = str(request.user.pk)
    standings = FinancialStandingFS.list_by_user(uid)
    return render(request, "budgeting/financial_standing_list.html", {"standings": standings})


@login_required
def financial_standing_add(request):
    if request.method == "POST":
        form = FinancialStandingFormFS(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            s = FinancialStandingFS(
                user_id=str(request.user.pk),
                snapshot_date=cd["snapshot_date"],
                total_assets=cd["total_assets"],
                current_assets=cd["current_assets"],
                fixed_assets=cd["fixed_assets"],
                total_liabilities=cd["total_liabilities"],
                short_term_liabilities=cd["short_term_liabilities"],
                long_term_liabilities=cd["long_term_liabilities"],
                notes=cd.get("notes") or "",
            )
            s.save()
            messages.success(request, "Financial standing snapshot added.")
            return redirect("budgeting:financial_standing_list")
    else:
        form = FinancialStandingFormFS(initial={"snapshot_date": date.today()})
    return render(request, "budgeting/financial_standing_form.html", {"form": form, "title": "Add snapshot"})


@login_required
def config_categories(request):
    """List categories and groups from Firestore."""
    groups = GroupFS.list_all()
    categories = CategoryFS.list_all()
    gmap = {g.pk: g for g in groups}
    # Group categories by group_id for template: list of (group, [(category, group_name), ...])
    by_group = {}
    for c in categories:
        gid = c.group_id or "_"
        if gid not in by_group:
            by_group[gid] = []
        by_group[gid].append((c, gmap.get(c.group_id).name if c.group_id in gmap else ""))
    grouped = [(g, by_group.get(g.pk, [])) for g in groups]
    return render(request, "budgeting/config_categories.html", {"grouped": grouped})


@login_required
def config_merchant_links(request):
    """List and add merchant → category links in Firestore."""
    uid = str(request.user.pk)
    links = MerchantCategoryLinkFS.list_by_user(uid)
    categories = CategoryFS.list_all()
    groups = {g.pk: g for g in GroupFS.list_all()}
    category_choices = [(c.pk, f"{groups.get(c.group_id).name if c.group_id in groups else ''} — {c.name}") for c in categories]
    for link in links:
        link.category_name = next((c.name for c in categories if c.pk == link.category_id), "—")
    if request.method == "POST":
        form = MerchantCategoryLinkFormFS(request.POST, category_choices=category_choices)
        if form.is_valid():
            cd = form.cleaned_data
            keyword_lower = (cd.get("keyword") or "").strip().lower()
            category_id = cd.get("category_id") or ""
            already_exists = any(
                (link.keyword or "").lower() == keyword_lower and (link.category_id or "") == category_id
                for link in links
            )
            if already_exists:
                form.add_error("keyword", "This keyword already exists for this category.")
            else:
                link = MerchantCategoryLinkFS(keyword=cd["keyword"], category_id=cd["category_id"], user_id=uid)
                link.save()
                messages.success(request, "Link added.")
                return redirect("budgeting:config_merchant_links")
    else:
        form = MerchantCategoryLinkFormFS(category_choices=category_choices)
    return render(request, "budgeting/config_merchant_links.html", {"links": links, "form": form})


@login_required
def config_merchant_links_edit(request, pk):
    """Edit an existing merchant → category link."""
    uid = str(request.user.pk)
    link = MerchantCategoryLinkFS.get(pk)
    if not link or link.user_id != uid:
        raise Http404("Link not found")
    categories = CategoryFS.list_all()
    groups = {g.pk: g for g in GroupFS.list_all()}
    category_choices = [(c.pk, f"{groups.get(c.group_id).name if c.group_id in groups else ''} — {c.name}") for c in categories]
    if request.method == "POST":
        form = MerchantCategoryLinkFormFS(request.POST, category_choices=category_choices)
        if form.is_valid():
            cd = form.cleaned_data
            keyword_lower = (cd.get("keyword") or "").strip().lower()
            category_id = cd.get("category_id") or ""
            # Check duplicate: same keyword+category for this user, excluding current link
            existing_links = MerchantCategoryLinkFS.list_by_user(uid)
            already_exists = any(
                l.pk != pk and (l.keyword or "").lower() == keyword_lower and (l.category_id or "") == category_id
                for l in existing_links
            )
            if already_exists:
                form.add_error("keyword", "This keyword already exists for this category.")
            else:
                link.keyword = cd["keyword"]
                link.category_id = cd["category_id"]
                link.save()
                messages.success(request, "Link updated.")
                return redirect("budgeting:config_merchant_links")
    else:
        form = MerchantCategoryLinkFormFS(category_choices=category_choices, initial={
            "keyword": link.keyword,
            "category_id": link.category_id or "",
        })
    return render(request, "budgeting/config_merchant_links_edit.html", {"form": form, "link": link})


@login_required
def config_merchant_links_delete(request, pk):
    """Delete a merchant → category link (POST only)."""
    if request.method != "POST":
        raise Http404("Invalid method")
    uid = str(request.user.pk)
    link = MerchantCategoryLinkFS.get(pk)
    if not link or link.user_id != uid:
        raise Http404("Link not found")
    link.delete()
    messages.success(request, "Link deleted.")
    return redirect("budgeting:config_merchant_links")


@login_required
def alert_list(request):
    """List open and resolved budget alerts; support resolve action."""
    uid = str(request.user.pk)
    today = date.today()
    year = int(request.GET.get("year", today.year))
    month = int(request.GET.get("month", today.month))
    _trigger_alert_eval(request.user, year, month)
    show = request.GET.get("show", "open")
    all_alerts = BudgetAlertFS.list_by_user(uid, open_only=False, limit=300)
    if show == "all":
        alerts = all_alerts
    elif show == "resolved":
        alerts = [a for a in all_alerts if a.is_resolved]
    else:
        alerts = [a for a in all_alerts if not a.is_resolved]
    categories = {c.pk: c for c in CategoryFS.list_all()}
    for a in alerts:
        cat = categories.get(a.category_id)
        a.category_name = cat.name if cat else (a.category_id or "—")
    return render(
        request,
        "budgeting/alert_list.html",
        {
            "alerts": alerts,
            "show": show,
            "year": year,
            "month": month,
            "years": list(range(today.year - 2, today.year + 3)),
        },
    )


@login_required
def alert_resolve(request, pk):
    if request.method != "POST":
        raise Http404("Invalid method")
    alert = resolve_alert(request.user, pk)
    if not alert:
        raise Http404("Alert not found")
    messages.success(request, "Alert resolved.")
    return redirect("budgeting:alert_list")


@login_required
def config_type_maps(request):
    """Configure expense consumption_type → budgeting category maps (user overrides)."""
    uid = str(request.user.pk)
    choices = _transaction_form_choices()
    # drop empty option for required category
    category_choices = [c for c in choices if c[0]]
    categories = {c.pk: c for c in CategoryFS.list_all()}
    user_maps = TypeCategoryMapFS.list_by_user(uid)
    global_maps = TypeCategoryMapFS.list_global()
    effective = TypeCategoryMapFS.get_map_for_user(uid)

    rows = []
    for ctype in CONSUMPTION_TYPES:
        cat_id = effective.get(ctype, "")
        cat = categories.get(cat_id)
        user_override = next((m for m in user_maps if m.consumption_type == ctype), None)
        rows.append({
            "consumption_type": ctype,
            "category_id": cat_id,
            "category_name": cat.name if cat else "—",
            "is_override": user_override is not None,
            "map_pk": user_override.pk if user_override else None,
        })

    if request.method == "POST":
        form = TypeCategoryMapFormFS(request.POST, category_choices=category_choices)
        if form.is_valid():
            cd = form.cleaned_data
            ctype = cd["consumption_type"]
            existing = next((m for m in user_maps if m.consumption_type == ctype), None)
            if existing:
                existing.category_id = cd["category_id"]
                existing.save()
            else:
                TypeCategoryMapFS(user_id=uid, consumption_type=ctype, category_id=cd["category_id"]).save()
            messages.success(request, f"Mapped {ctype} → category.")
            return redirect("budgeting:config_type_maps")
    else:
        form = TypeCategoryMapFormFS(category_choices=category_choices)

    return render(
        request,
        "budgeting/config_type_maps.html",
        {"rows": rows, "form": form, "global_count": len(global_maps)},
    )


@login_required
def config_type_maps_clear(request, pk):
    """Remove a user override type map (falls back to global)."""
    if request.method != "POST":
        raise Http404("Invalid method")
    uid = str(request.user.pk)
    m = TypeCategoryMapFS.get(pk)
    if not m or m.user_id != uid:
        raise Http404("Map not found")
    m.delete()
    messages.success(request, "Override cleared; using global default.")
    return redirect("budgeting:config_type_maps")


@login_required
def config_thresholds(request):
    """Edit global and per-category utilization thresholds + email toggle."""
    uid = str(request.user.pk)
    choices = _transaction_form_choices()
    category_choices = [c for c in choices if c[0]]
    thresholds = BudgetThresholdFS.list_by_user(uid)
    categories = {c.pk: c for c in CategoryFS.list_all()}
    for t in thresholds:
        if t.category_id:
            cat = categories.get(t.category_id)
            t.category_name = cat.name if cat else t.category_id
        else:
            t.category_name = "Global default"

    if request.method == "POST":
        form = BudgetThresholdFormFS(request.POST, category_choices=category_choices)
        if form.is_valid():
            cd = form.cleaned_data
            cat_id = (cd.get("category_id") or "").strip() or None
            existing = None
            for t in thresholds:
                if (t.category_id or None) == cat_id:
                    existing = t
                    break
            if existing:
                existing.warn_pct = cd["warn_pct"]
                existing.critical_pct = cd["critical_pct"]
                existing.email_enabled = bool(cd.get("email_enabled"))
                existing.save()
            else:
                BudgetThresholdFS(
                    user_id=uid,
                    category_id=cat_id,
                    warn_pct=cd["warn_pct"],
                    critical_pct=cd["critical_pct"],
                    email_enabled=bool(cd.get("email_enabled")),
                ).save()
            messages.success(request, "Threshold saved.")
            return redirect("budgeting:config_thresholds")
    else:
        global_t = BudgetThresholdFS.get_global_for_user(uid)
        form = BudgetThresholdFormFS(
            category_choices=category_choices,
            initial={
                "warn_pct": global_t.warn_pct if global_t else 80,
                "critical_pct": global_t.critical_pct if global_t else 100,
                "email_enabled": global_t.email_enabled if global_t else True,
            },
        )

    return render(
        request,
        "budgeting/config_thresholds.html",
        {"thresholds": thresholds, "form": form},
    )


@login_required
def config_thresholds_delete(request, pk):
    if request.method != "POST":
        raise Http404("Invalid method")
    uid = str(request.user.pk)
    t = BudgetThresholdFS.get(pk)
    if not t or t.user_id != uid:
        raise Http404("Threshold not found")
    t.delete()
    messages.success(request, "Threshold deleted.")
    return redirect("budgeting:config_thresholds")

