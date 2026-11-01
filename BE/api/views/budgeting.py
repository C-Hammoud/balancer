from calendar import month_name
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.exceptions import ParseError
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from api.serializers import (
    BudgetForecastSerializer,
    BudgetThresholdSerializer,
    CategorySerializer,
    CommitmentSerializer,
    FinancialStandingSerializer,
    GroupSerializer,
    IncomeSourceSerializer,
    MarkPaymentSerializer,
    MerchantLinkSerializer,
    SavingsSerializer,
    ScheduleLineUpdateSerializer,
    TransactionSerializer,
    TypeCategoryMapSerializer,
)
from api.utils import decimal_to_json, transaction_to_dict, trigger_budget_alerts, user_id
from api.currency import resolve_report_currency
from budgeting.alert_state import alert_is_snoozed, alert_state
from budgeting.category_access import (
    can_edit,
    get_visible_category,
    get_visible_group,
    visible_categories,
    visible_groups,
)
from budgeting.alerts import (
    SNOOZE_DAY_CHOICES,
    alert_counts,
    process_budget_alerts,
    refresh_alerts_for_user,
    reopen_alert,
    resolve_alert,
    snooze_alert,
    unsnooze_alert,
)
from budgeting.commitment_schedule import (
    ensure_schedule,
    evaluate_commitment_reminders,
    generate_schedule_lines,
    line_to_dict,
    mark_line_outstanding,
    mark_line_paid,
    record_line_payment,
    reverse_line_payment,
    schedule_progress,
    sync_payment_date,
)
from budgeting.store import (
    BudgetAlertFS,
    BudgetFS,
    BudgetThresholdFS,
    CategoryFS,
    CommitmentFS,
    CommitmentScheduleLineFS,
    FinancialStandingFS,
    GroupFS,
    IncomeSourceFS,
    MerchantCategoryLinkFS,
    SavingsFS,
    TransactionFS,
    TypeCategoryMapFS,
    CONSUMPTION_TYPES,
)
from budgeting.models import GoalStatus
from budgeting.plan_triggers import on_commitment_change
from budgeting.services import (
    actual_expense_total,
    actual_income_total,
    apply_merchant_link_to_transactions,
    budget_utilization_report,
    categories_and_groups_for_user,
    effective_group_forecast,
    get_month_str,
    merchant_key_from_description,
    savings_actual,
    sub_forecast_sum,
    suggest_category_for_description,
    yearly_overview_report,
)


def _parse_account_id(data) -> str:
    if not isinstance(data, dict):
        return ""
    return (data.get("account_id") or data.get("income_source_id") or "").strip()


def _account_to_dict(s) -> dict:
    return {
        "id": s.pk,
        "name": s.name,
        "account_type": getattr(s, "account_type", "bank") or "bank",
        "order": s.order,
        "is_active": s.is_active,
        "is_default_for_expenses": bool(getattr(s, "is_default_for_expenses", False)),
    }


def _clear_expense_default_accounts(uid: str, except_pk: str | None = None) -> None:
    for acc in IncomeSourceFS.list_by_user(uid):
        if except_pk and acc.pk == except_pk:
            continue
        if getattr(acc, "is_default_for_expenses", False):
            acc.is_default_for_expenses = False
            acc.save()


def _query_int(request, name: str, default: int) -> int:
    """Integer query parameter; a malformed value is a 400, not a server error."""
    raw = request.query_params.get(name)
    if raw is None:
        return int(default)
    try:
        return int(str(raw).strip())
    except ValueError:
        raise ParseError(f"Invalid number: {raw}")


def _resolve_account(uid: str, account_id: str):
    if not account_id:
        return None, {"account_id": ["Select the account this transaction was done from."]}
    acc = IncomeSourceFS.get(account_id)
    if not acc or acc.user_id != uid:
        return None, {"account_id": ["Account not found."]}
    return acc, None


class BudgetingDashboardView(APIView):
    def get(self, request):
        today = date.today()
        year = _query_int(request, "year", today.year)
        month = _query_int(request, "month", today.month)
        refresh_alerts_for_user(request.user, year, month, force=False)
        report_currency = resolve_report_currency(
            request.user, request.query_params.get("report_currency")
        )
        report = budget_utilization_report(
            request.user, year, month, report_currency=report_currency
        )
        open_alerts = [
            a for a in BudgetAlertFS.list_by_user(user_id(request.user), open_only=True, limit=200)
            if a.year == year and a.month == month and not alert_is_snoozed(a)
        ]
        return Response(decimal_to_json({
            "year": year,
            "month": month,
            "report_currency": report_currency,
            "report": report,
            "income_total": actual_income_total(
                request.user, year, month, report_currency=report_currency
            ),
            "expense_total": actual_expense_total(
                request.user, year, month, report_currency=report_currency
            ),
            "open_alerts": [
                {
                    "id": a.pk,
                    "severity": a.severity,
                    "title": a.title,
                    "description": a.description,
                    "alert_type": getattr(a, "alert_type", None) or "utilization",
                    "category_id": a.category_id,
                    "utilization_pct": a.utilization_pct,
                    "is_resolved": a.is_resolved,
                }
                for a in open_alerts
            ],
        }))


class YearlyOverviewView(APIView):
    """Year-level series for dashboard: each month's income, expense, util, remaining."""

    def get(self, request):
        today = date.today()
        year = _query_int(request, "year", today.year)
        report_currency = resolve_report_currency(
            request.user, request.query_params.get("report_currency")
        )
        payload = yearly_overview_report(
            request.user, year, report_currency=report_currency
        )
        for row in payload["months"]:
            m = row["month"]
            row["month_name"] = month_name[m]
            row["month_short"] = month_name[m][:3]
        return Response(decimal_to_json(payload))


class UtilizationReportView(APIView):
    def get(self, request):
        today = date.today()
        year = _query_int(request, "year", today.year)
        month = _query_int(request, "month", today.month)
        report_currency = resolve_report_currency(
            request.user, request.query_params.get("report_currency")
        )
        return Response(
            decimal_to_json(
                budget_utilization_report(
                    request.user, year, month, report_currency=report_currency
                )
            )
        )


class CategoryGroupListView(APIView):
    def get(self, request):
        groups_list, categories_by_id = categories_and_groups_for_user(request.user)
        return Response({
            "groups": [_group_dict(g, request.user) for g in groups_list],
            "categories": [
                _category_dict(c, getattr(c, "group_name", ""), request.user)
                for c in categories_by_id.values()
            ],
        })


def _ownership(obj, user) -> dict:
    """Shared defaults are read-only for normal users; their own items are editable."""
    return {
        "is_shared": not (getattr(obj, "user_id", "") or ""),
        "can_edit": can_edit(obj, user),
    }


def _group_dict(g: GroupFS, user=None):
    out = {"id": g.pk, "name": g.name, "order": g.order}
    if user is not None:
        out.update(_ownership(g, user))
    return out


def _category_dict(c: CategoryFS, group_name: str = "", user=None):
    out = {
        "id": c.pk,
        "name": c.name,
        "group_id": c.group_id,
        "group_name": group_name,
        "include_in_reports": c.include_in_reports,
        "order": c.order,
    }
    if user is not None:
        out.update(_ownership(c, user))
    return out


def _merchant_link_dict(link: MerchantCategoryLinkFS, categories_by_id, groups):
    """Serialize a merchant link with subcategory and parent group names."""
    cat = categories_by_id.get(link.category_id)
    group_id = ""
    group_name = ""
    category_name = ""
    if cat:
        category_name = cat.name
        group_id = cat.group_id or ""
        g = groups.get(group_id)
        group_name = g.name if g else getattr(cat, "group_name", "")
    return {
        "id": link.pk,
        "keyword": link.keyword,
        "category_id": link.category_id,
        "category_name": category_name,
        "group_id": group_id,
        "group_name": group_name,
    }


def _require_subcategory(user, category_id: str):
    """
    Merchant links and expense transactions use subcategories (CategoryFS), not parent groups.
    Returns the CategoryFS only if it exists and is visible to `user` (shared or their own).

    Category and group tables each have their own numeric ids (1, 2, 3…), so the same
    number can exist in both. Always resolve a subcategory id via CategoryFS first.
    """
    return get_visible_category(user, category_id)


def _category_id_field_error(user, category_id: str) -> str:
    """Human-readable validation message when category_id is not a usable subcategory."""
    g = get_visible_group(user, category_id)
    if g:
        subs = sorted(
            (c for c in visible_categories(user) if c.group_id == g.pk),
            key=lambda c: (c.order, c.name.lower()),
        )
        if subs:
            examples = ", ".join(c.name for c in subs[:6])
            return (
                f'"{g.name}" is a parent category, not a subcategory (merchant). '
                f'Pick one under it, e.g. {examples}.'
            )
        return (
            f'"{g.name}" is a parent category with no subcategories yet. '
            "Add merchants under Setup → Categories first."
        )
    return (
        f'Subcategory id "{category_id}" was not found. '
        "Choose a merchant (subcategory) under a parent category."
    )


def _wants_shared(request) -> bool:
    """Staff may create shared defaults by sending {"shared": true}."""
    flag = request.data.get("shared") in (True, "true", "1", 1)
    return flag and bool(getattr(request.user, "is_staff", False))


_READ_ONLY_SHARED = "Shared default categories can only be changed by an administrator."


class GroupListCreateView(APIView):
    """Parent categories (groups). Multiple subcategories belong to one parent."""

    def get(self, request):
        groups = sorted(visible_groups(request.user), key=lambda g: (g.order, g.name.lower()))
        return Response([_group_dict(g, request.user) for g in groups])

    def post(self, request):
        serializer = GroupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        name = cd["name"].strip()
        if not name:
            return Response({"name": ["Name is required."]}, status=status.HTTP_400_BAD_REQUEST)
        existing = [g for g in visible_groups(request.user) if g.name.lower() == name.lower()]
        if existing:
            return Response({"name": ["A category with this name already exists."]}, status=status.HTTP_400_BAD_REQUEST)
        owner = "" if _wants_shared(request) else user_id(request.user)
        g = GroupFS(name=name, order=cd.get("order", 0), user_id=owner)
        g.save()
        return Response(_group_dict(g, request.user), status=status.HTTP_201_CREATED)


class GroupDetailView(APIView):
    def patch(self, request, pk):
        g = get_visible_group(request.user, pk)
        if not g:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_edit(g, request.user):
            return Response({"detail": _READ_ONLY_SHARED}, status=status.HTTP_403_FORBIDDEN)
        serializer = GroupSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        if "name" in cd:
            name = cd["name"].strip()
            if not name:
                return Response({"name": ["Name is required."]}, status=status.HTTP_400_BAD_REQUEST)
            clash = [x for x in visible_groups(request.user) if x.pk != pk and x.name.lower() == name.lower()]
            if clash:
                return Response({"name": ["A category with this name already exists."]}, status=status.HTTP_400_BAD_REQUEST)
            g.name = name
        if "order" in cd:
            g.order = cd["order"]
        g.save()
        return Response(_group_dict(g, request.user))

    def delete(self, request, pk):
        g = get_visible_group(request.user, pk)
        if not g:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_edit(g, request.user):
            return Response({"detail": _READ_ONLY_SHARED}, status=status.HTTP_403_FORBIDDEN)
        # Any owner's subcategories block deletion (a shared group may hold users' subcategories).
        children = [c for c in CategoryFS.list_all(limit=5000) if c.group_id == pk]
        if children:
            return Response(
                {"detail": f"Remove or reassign {len(children)} subcategory(ies) before deleting this category."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        g.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CategoryListCreateView(APIView):
    """Subcategories under a parent category (group)."""

    def get(self, request):
        groups = {g.pk: g for g in visible_groups(request.user)}
        cats = sorted(visible_categories(request.user), key=lambda c: (c.order, c.name.lower()))
        group_id = (request.query_params.get("group_id") or "").strip()
        if group_id:
            cats = [c for c in cats if c.group_id == group_id]
        return Response([
            _category_dict(c, groups.get(c.group_id).name if c.group_id in groups else "", request.user)
            for c in cats
        ])

    def post(self, request):
        serializer = CategorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        group = get_visible_group(request.user, cd["group_id"])
        if not group:
            return Response({"group_id": ["Parent category not found."]}, status=status.HTTP_400_BAD_REQUEST)
        name = cd["name"].strip()
        if not name:
            return Response({"name": ["Name is required."]}, status=status.HTTP_400_BAD_REQUEST)
        clash = [
            c for c in visible_categories(request.user)
            if c.group_id == group.pk and c.name.lower() == name.lower()
        ]
        if clash:
            return Response(
                {"name": ["A subcategory with this name already exists under this category."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Users may add their own subcategories under shared groups.
        shared = _wants_shared(request) and not (group.user_id or "")
        c = CategoryFS(
            name=name,
            group_id=group.pk,
            include_in_reports=cd.get("include_in_reports", True),
            order=cd.get("order", 0),
            user_id="" if shared else user_id(request.user),
        )
        c.save()
        return Response(_category_dict(c, group.name, request.user), status=status.HTTP_201_CREATED)


class CategoryDetailView(APIView):
    def patch(self, request, pk):
        c = get_visible_category(request.user, pk)
        if not c:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_edit(c, request.user):
            return Response({"detail": _READ_ONLY_SHARED}, status=status.HTTP_403_FORBIDDEN)
        serializer = CategorySerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        if "group_id" in cd:
            group = get_visible_group(request.user, cd["group_id"])
            if not group:
                return Response({"group_id": ["Parent category not found."]}, status=status.HTTP_400_BAD_REQUEST)
            if not (c.user_id or "") and (group.user_id or ""):
                return Response(
                    {"group_id": ["A shared subcategory cannot move under a personal category."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            c.group_id = group.pk
        group = GroupFS.get(c.group_id)
        group_name = group.name if group else ""
        if "name" in cd:
            name = cd["name"].strip()
            if not name:
                return Response({"name": ["Name is required."]}, status=status.HTTP_400_BAD_REQUEST)
            clash = [
                x for x in visible_categories(request.user)
                if x.pk != pk and x.group_id == c.group_id and x.name.lower() == name.lower()
            ]
            if clash:
                return Response(
                    {"name": ["A subcategory with this name already exists under this category."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            c.name = name
        if "include_in_reports" in cd:
            c.include_in_reports = cd["include_in_reports"]
        if "order" in cd:
            c.order = cd["order"]
        c.save()
        return Response(_category_dict(c, group_name, request.user))

    def delete(self, request, pk):
        c = get_visible_category(request.user, pk)
        if not c:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if not can_edit(c, request.user):
            return Response({"detail": _READ_ONLY_SHARED}, status=status.HTTP_403_FORBIDDEN)
        # Clear type maps pointing at this subcategory
        for m in TypeCategoryMapFS.list_all(limit=5000):
            if m.category_id == pk:
                m.delete()
        c.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _budget_link_access_error(user, budget_id: str):
    if not budget_id:
        return None
    try:
        from budgeting.personal_budget_access import require_edit
        require_edit(user, budget_id)
    except PermissionError as exc:
        return str(exc) or "You do not have permission to modify this budget."
    return None


def _transaction_access(user, t):
    if not t:
        return None
    if t.user_id == user_id(user):
        return t
    bid = (getattr(t, "budget_id", None) or "").strip()
    if bid:
        try:
            from budgeting.personal_budget_access import require_edit
            require_edit(user, bid)
            return t
        except PermissionError:
            return None
    return None


class TransactionListCreateView(APIView):
    def get(self, request):
        month = request.query_params.get("month")
        txns = TransactionFS.list_by_user(user_id(request.user), month=month)
        return Response([transaction_to_dict(t) for t in txns])

    def post(self, request):
        serializer = TransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        direction = cd["direction"]
        category_id = cd.get("category_id") or None
        account_id = _parse_account_id(cd)
        commitment_id = (cd.get("commitment_id") or "").strip() or None
        schedule_line_id = (cd.get("schedule_line_id") or "").strip() or None
        include_in_utilization = bool(cd.get("include_in_utilization", False))
        budget_id = (cd.get("budget_id") or "").strip() or None
        budget_category_id = (cd.get("budget_category_id") or "").strip() or None
        if budget_id:
            err = _budget_link_access_error(request.user, budget_id)
            if err:
                return Response({"budget_id": [err]}, status=status.HTTP_403_FORBIDDEN)
        amount = cd["amount"]
        txn_date = cd["date"]
        description = cd["description"]
        note = (cd.get("note") or "").strip()
        txn_currency = cd.get("currency") or "USD"
        source_account = ""

        acc, acc_err = _resolve_account(user_id(request.user), account_id)
        if acc_err:
            return Response(acc_err, status=status.HTTP_400_BAD_REQUEST)
        source_account = acc.name
        income_source_id = acc.pk

        to_account_id = cd.get("to_account_id") or ""
        if to_account_id:
            dest, dest_err = _resolve_account(user_id(request.user), to_account_id)
            if dest_err:
                return Response({"to_account_id": dest_err["account_id"]}, status=status.HTTP_400_BAD_REQUEST)
            to_account_id = dest.pk

        paid_line = None
        if commitment_id:
            c = CommitmentFS.get(commitment_id)
            if not c or c.user_id != user_id(request.user):
                return Response({"commitment_id": ["Commitment not found."]}, status=status.HTTP_400_BAD_REQUEST)
            progress = schedule_progress(c)
            if schedule_line_id:
                paid_line = next(
                    (l for l in progress["lines"] if l.pk == schedule_line_id and l.status == "outstanding"),
                    None,
                )
            if not paid_line:
                outstanding = [l for l in progress["lines"] if l.status == "outstanding"]
                paid_line = outstanding[0] if outstanding else None
            if not paid_line:
                return Response(
                    {"commitment_id": ["No outstanding payment on this commitment."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            amount = paid_line.amount
            schedule_line_id = paid_line.pk
            direction = "expense"
            if not description or description.lower() == "unassigned":
                description = c.name
            if not note:
                note = f"Commitment payment — {c.name}"
            if paid_line.due_date and not request.data.get("date"):
                txn_date = paid_line.due_date
            txn_currency = getattr(c, "currency", None) or txn_currency or "USD"

        if direction == "income":
            category_id = None
            commitment_id = None
            schedule_line_id = None
            if not (description or "").strip():
                return Response(
                    {"description": ["Enter what this income is (e.g. Salary)."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        elif direction == "transfer" and to_account_id:
            # Moving money between own accounts is not spending: no category.
            category_id = None
        else:
            if category_id:
                sub = _require_subcategory(request.user, category_id)
                if not sub:
                    return Response(
                        {"category_id": [_category_id_field_error(request.user, category_id)]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                category_id = sub.pk
            if not commitment_id and not category_id and description:
                suggested = suggest_category_for_description(description, request.user)
                if suggested:
                    category_id = suggested.pk

        ext_id = ""
        if schedule_line_id:
            ext_id = f"commitment_line:{schedule_line_id}"
            if TransactionFS.exists_by_external_id(user_id(request.user), ext_id):
                return Response(
                    {"commitment_id": ["This installment was already recorded as a transaction."]},
                    status=status.HTTP_409_CONFLICT,
                )

        t = TransactionFS(
            user_id=user_id(request.user),
            date=txn_date,
            month=get_month_str(txn_date),
            description=description[:500],
            category_id=category_id,
            classification=None,
            amount=amount,
            currency=txn_currency,
            note=note,
            time=(cd.get("time") or datetime.now().strftime("%H:%M"))[:8],
            direction=direction,
            source_account=source_account,
            income_source_id=income_source_id or "",
            commitment_id=commitment_id or "",
            schedule_line_id=schedule_line_id or "",
            external_id=ext_id,
            include_in_utilization=include_in_utilization,
            budget_id=budget_id or "",
            budget_category_id=budget_category_id or "",
            to_account_id=to_account_id or "",
            status=cd.get("status") or "settled",
        )
        t.save()
        if paid_line:
            mark_line_paid(paid_line, txn_date)
        if direction != "transfer":
            trigger_budget_alerts(request.user, t.date.year if t.date else None, t.date.month if t.date else None)
        return Response(transaction_to_dict(t), status=status.HTTP_201_CREATED)


class TransactionDetailView(APIView):
    def _get(self, request, pk):
        t = TransactionFS.get(pk)
        return _transaction_access(request.user, t)

    def get(self, request, pk):
        t = self._get(request, pk)
        if not t:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(transaction_to_dict(t))

    def patch(self, request, pk):
        t = self._get(request, pk)
        if not t:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        for field in (
            "date",
            "time",
            "description",
            "category_id",
            "classification",
            "amount",
            "currency",
            "note",
            "direction",
            "source_account",
            "account_id",
            "income_source_id",
            "budget_id",
            "budget_category_id",
            "to_account_id",
            "status",
        ):
            if field not in request.data:
                continue
            val = request.data[field]
            if field in ("budget_id", "budget_category_id"):
                val = (val or "").strip()
                setattr(t, field, val)
                continue
            if field == "status":
                if val not in ("settled", "pending"):
                    return Response({"status": ['"%s" is not a valid choice.' % val]}, status=status.HTTP_400_BAD_REQUEST)
                t.status = val
                continue
            if field == "to_account_id":
                val = (val or "").strip()
                if val:
                    dest, dest_err = _resolve_account(user_id(request.user), val)
                    if dest_err:
                        return Response({"to_account_id": dest_err["account_id"]}, status=status.HTTP_400_BAD_REQUEST)
                    val = dest.pk
                t.to_account_id = val
                continue
            if field in ("account_id", "income_source_id"):
                val = (val or "").strip()
                if not val:
                    # Partial update: omit or empty means leave account unchanged.
                    continue
                acc, acc_err = _resolve_account(user_id(request.user), val)
                if acc_err:
                    return Response(acc_err, status=status.HTTP_400_BAD_REQUEST)
                t.income_source_id = acc.pk
                t.source_account = acc.name
                continue
            if field == "date" and isinstance(val, str):
                try:
                    val = date.fromisoformat(val[:10])
                except ValueError:
                    return Response(
                        {"date": ["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            if field == "category_id" and val == "":
                val = None
            if field == "amount":
                try:
                    val = Decimal(str(val).strip())
                    if not val.is_finite():
                        raise InvalidOperation
                except InvalidOperation:
                    return Response({"amount": ["A valid number is required."]}, status=status.HTTP_400_BAD_REQUEST)
            if field == "time":
                val = (val or "")[:8]
            if field == "note":
                val = val or ""
            if field == "currency":
                val = val or "USD"
            setattr(t, field, val)
        if t.direction == "income":
            t.category_id = None
            if not (t.description or "").strip():
                return Response(
                    {"description": ["Enter what this income is (e.g. Salary)."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            # Validate only a newly chosen category: a shared-budget editor may keep
            # the owner's existing category without being able to see it.
            if t.category_id and "category_id" in request.data:
                sub = _require_subcategory(request.user, t.category_id)
                if not sub:
                    return Response(
                        {"category_id": [_category_id_field_error(request.user, t.category_id)]},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                t.category_id = sub.pk
        if t.direction != "transfer":
            t.to_account_id = ""
        elif t.to_account_id and t.to_account_id == t.income_source_id:
            return Response(
                {"to_account_id": ["Choose a different account to transfer to."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        elif t.to_account_id:
            # A one-row transfer moves money between own accounts: it is not spending.
            t.category_id = None
        if (t.budget_id or "").strip():
            err = _budget_link_access_error(request.user, t.budget_id)
            if err:
                return Response({"budget_id": [err]}, status=status.HTTP_403_FORBIDDEN)
        if t.date:
            t.month = get_month_str(t.date)
        t.save()
        trigger_budget_alerts(request.user, t.date.year if t.date else None, t.date.month if t.date else None)
        return Response(transaction_to_dict(t))

    def delete(self, request, pk):
        t = self._get(request, pk)
        if not t:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        year = t.date.year if t.date else None
        month = t.date.month if t.date else None
        line_id = (getattr(t, "schedule_line_id", "") or "").strip()
        t.delete()
        if line_id:
            # The installment is no longer paid once its payment is deleted.
            line = CommitmentScheduleLineFS.get(line_id)
            if line and line.status == "paid":
                mark_line_outstanding(line)
        trigger_budget_alerts(request.user, year, month)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TransactionUploadView(APIView):
    """
    Import a bank statement (.csv or .xlsx). Optional form fields:
      date_format: auto | dmy | mdy | ymd (auto: detect from the file, else the user's country)
      currency:    statement currency (default: the user's default currency)
      account_id:  account the statement belongs to
    Positive amounts are income and negative amounts are expenses (or use Debit/Credit columns).
    """

    parser_classes = [MultiPartParser]

    def post(self, request):
        from django.conf import settings as dj_settings

        from api.locale_defaults import VALID_CURRENCIES
        from api.user_preferences import get_user_preferences
        from budgeting import importer

        f = request.FILES.get("file")
        if not f:
            return Response({"detail": "Choose a .csv or .xlsx file."}, status=status.HTTP_400_BAD_REQUEST)
        if f.size and f.size > dj_settings.TRANSACTION_IMPORT_MAX_BYTES:
            limit_mb = dj_settings.TRANSACTION_IMPORT_MAX_BYTES // (1024 * 1024)
            return Response({"detail": f"File is too large (max {limit_mb} MB)."}, status=status.HTTP_400_BAD_REQUEST)

        uid = user_id(request.user)
        prefs = get_user_preferences(request.user)

        currency = (request.data.get("currency") or prefs.get("default_currency") or "USD").strip().upper()
        if currency not in VALID_CURRENCIES:
            return Response({"currency": ["Unsupported currency."]}, status=status.HTTP_400_BAD_REQUEST)
        date_format = (request.data.get("date_format") or "auto").strip().lower()
        if date_format not in importer.DATE_FORMATS:
            return Response(
                {"date_format": ["Use one of: " + ", ".join(importer.DATE_FORMATS) + "."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        acc = None
        account_id = _parse_account_id(request.data)
        if account_id:
            acc, acc_err = _resolve_account(uid, account_id)
            if acc_err:
                return Response(acc_err, status=status.HTTP_400_BAD_REQUEST)

        try:
            rows = importer.read_rows(f.name, f.read())
        except importer.StatementImportError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        if len(rows) > dj_settings.TRANSACTION_IMPORT_MAX_ROWS + 1:
            return Response(
                {"detail": f"Too many rows (max {dj_settings.TRANSACTION_IMPORT_MAX_ROWS}). Split the file."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        col_map = importer.column_map(rows[0]) if rows else None
        data_rows = rows[1:] if col_map else rows
        if date_format == "auto":
            fallback = importer.default_date_format(prefs.get("country"))
            date_idx = col_map["date"] if col_map else 0
            date_format = importer.guess_date_format(
                (r[date_idx] for r in data_rows if len(r) > date_idx), fallback
            )

        created = skipped = matched = 0
        errors = []
        unmatched_map = {}
        months_touched: set[tuple[int, int]] = set()
        occurrences: dict[str, int] = {}

        for row_no, row in enumerate(data_rows, start=2 if col_map else 1):
            if not any((c or "").strip() for c in row):
                continue
            try:
                date_str, desc, amt_str = importer.extract_fields(row, col_map)
            except (IndexError, AttributeError, ValueError):
                skipped += 1
                errors.append({"row": row_no, "error": "Missing date, description or amount."})
                continue
            if date_str.lower() in importer.HEADER_ALIASES["date"]:
                continue
            try:
                txn_date = importer.parse_date(date_str, date_format)
                amount = importer.parse_amount(amt_str)
            except ValueError:
                skipped += 1
                errors.append({"row": row_no, "error": "Could not read date or amount: " + date_str + " / " + amt_str})
                continue
            direction = "income" if amount > 0 else "expense"
            amount = abs(amount)
            base = importer.dedupe_key(txn_date, amount, desc, 1)
            occurrences[base] = occurrences.get(base, 0) + 1
            ext_id = importer.dedupe_key(txn_date, amount, desc, occurrences[base])
            if TransactionFS.exists_by_external_id(uid, ext_id):
                skipped += 1
                continue

            cat = suggest_category_for_description(desc, request.user) if direction == "expense" else None

            t = TransactionFS(
                user_id=uid,
                date=txn_date,
                month=get_month_str(txn_date),
                description=desc[:500],
                amount=amount,
                currency=currency,
                direction=direction,
                category_id=cat.pk if cat else None,
                external_id=ext_id,
                source_account=acc.name if acc else "",
                income_source_id=acc.pk if acc else "",
            )
            t.save()
            created += 1
            months_touched.add((txn_date.year, txn_date.month))

            if direction == "expense":
                if cat:
                    matched += 1
                else:
                    merchant = merchant_key_from_description(desc)
                    key = merchant.lower()
                    if not key:
                        continue
                    bucket = unmatched_map.get(key)
                    if not bucket:
                        parts = [p for p in merchant.split() if not p.replace(".", "").isdigit()]
                        suggestion = " ".join(parts[:3]) if parts else merchant
                        bucket = {
                            "merchant": merchant,
                            "keyword_suggestion": suggestion[:80],
                            "count": 0,
                            "transaction_ids": [],
                            "sample_descriptions": [],
                        }
                        unmatched_map[key] = bucket
                    bucket["count"] += 1
                    bucket["transaction_ids"].append(t.pk)
                    if len(bucket["sample_descriptions"]) < 3 and desc not in bucket["sample_descriptions"]:
                        bucket["sample_descriptions"].append(desc[:120])

        alert_emails_sent = 0
        if created > 0:
            # Cover every month present in the file, then email new alerts immediately
            for y, m in sorted(months_touched):
                refresh_alerts_for_user(request.user, y, m, force=True)
            stats = process_budget_alerts(user=request.user)
            alert_emails_sent = stats.get("emails_sent", 0)
        unmatched = sorted(unmatched_map.values(), key=lambda x: (-x["count"], x["merchant"].lower()))
        return Response({
            "created": created,
            "skipped": skipped,
            "matched": matched,
            "unmatched_count": len(unmatched),
            "unmatched": unmatched,
            "alerts_emails_sent": alert_emails_sent,
            "date_format": date_format,
            "currency": currency,
            "errors": errors[:20],
        })


class BudgetListView(APIView):
    def get(self, request):
        today = date.today()
        year = _query_int(request, "year", today.year)
        month = _query_int(request, "month", today.month)
        from budgeting.services import actual_expense_by_category

        uid = user_id(request.user)
        groups_list, categories_by_id = categories_and_groups_for_user(request.user)
        groups_map = {g.pk: g for g in groups_list}
        budgets = BudgetFS.list_by_user(uid, year=year, month=month)
        actuals = actual_expense_by_category(request.user, year, month)

        group_budgets = {
            b.group_id: b for b in budgets if (b.group_id or "").strip() and not (b.category_id or "").strip()
        }
        cat_budgets = {b.category_id: b for b in budgets if (b.category_id or "").strip()}

        rows = []
        for g in sorted(groups_list, key=lambda x: (x.order, x.name.lower())):
            subs = [
                c for c in categories_by_id.values()
                if c.group_id == g.pk and c.include_in_reports
            ]
            if not subs:
                continue
            group_actual = Decimal("0")
            sub_budgets = []
            for cat in sorted(subs, key=lambda c: (c.order, c.name.lower())):
                act = actuals.get(cat.pk) or Decimal("0")
                group_actual += act
                sb = cat_budgets.get(cat.pk)
                sub_budgets.append({
                    "category_id": cat.pk,
                    "category_name": cat.name,
                    "forecast": sb.forecast if sb else Decimal("0"),
                    "actual": act,
                })
            sub_sum = sub_forecast_sum(cat_budgets, subs)
            gb = group_budgets.get(g.pk)
            effective = effective_group_forecast(gb, sub_sum)
            explicit = (
                gb.forecast
                if gb and (gb.forecast or Decimal("0")) > Decimal("0")
                else None
            )
            if gb or sub_budgets or group_actual > 0 or sub_sum > 0:
                rows.append({
                    "group_id": g.pk,
                    "category_id": None,
                    "category_name": g.name,
                    "forecast": effective,
                    "forecast_explicit": explicit,
                    "forecast_from_subs": sub_sum,
                    "forecast_is_derived": explicit is None and sub_sum > Decimal("0"),
                    "actual": group_actual,
                    "sub_budgets": sub_budgets,
                })
        return Response(decimal_to_json({"year": year, "month": month, "rows": rows}))


class BudgetGroupDetailView(APIView):
    """Monthly forecast for a parent category (group); subcategory budgets are optional."""

    def patch(self, request, year, month, group_id):
        uid = user_id(request.user)
        group = get_visible_group(request.user, group_id)
        if not group:
            return Response({"detail": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        b = BudgetFS.get_by_user_group_month(uid, str(group_id), int(year), int(month))
        if not b:
            b = BudgetFS(
                user_id=uid,
                group_id=str(group_id),
                category_id="",
                year=int(year),
                month=int(month),
                forecast=Decimal("0"),
            )
        serializer = BudgetForecastSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        b.forecast = serializer.validated_data["forecast"]
        b.save()
        trigger_budget_alerts(request.user, int(year), int(month))
        return Response(
            decimal_to_json({
                "forecast": b.forecast,
                "group_id": group_id,
                "year": year,
                "month": month,
            })
        )


class BudgetDetailView(APIView):
    def get(self, request, year, month, category_id):
        uid = user_id(request.user)
        b = BudgetFS.get_by_user_category_month(uid, str(category_id), int(year), int(month))
        if not b:
            b = BudgetFS(
                user_id=uid,
                category_id=str(category_id),
                group_id="",
                year=int(year),
                month=int(month),
                forecast=Decimal("0"),
            )
            b.save()
        return Response(
            decimal_to_json({
                "forecast": b.forecast,
                "category_id": category_id,
                "year": year,
                "month": month,
            })
        )

    def patch(self, request, year, month, category_id):
        uid = user_id(request.user)
        if not get_visible_category(request.user, str(category_id)):
            return Response({"detail": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        b = BudgetFS.get_by_user_category_month(uid, str(category_id), int(year), int(month))
        if not b:
            b = BudgetFS(
                user_id=uid,
                category_id=str(category_id),
                group_id="",
                year=int(year),
                month=int(month),
                forecast=Decimal("0"),
            )
        serializer = BudgetForecastSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        b.forecast = serializer.validated_data["forecast"]
        b.save()
        trigger_budget_alerts(request.user, int(year), int(month))
        return Response(decimal_to_json({"forecast": b.forecast}))


class SavingsListView(APIView):
    def get(self, request):
        uid = user_id(request.user)
        data = SavingsFS.list_by_user(uid)
        goal_labels = dict(GoalStatus.choices)
        report_currency = resolve_report_currency(request.user, request.query_params.get("report_currency"))
        out = []
        for s in data:
            actual = (
                s.actual if s.actual is not None
                else savings_actual(request.user, s.year, s.month, report_currency=report_currency)
            )
            out.append(decimal_to_json({
                "year": s.year,
                "month": s.month,
                "report_currency": report_currency,
                "target": s.target,
                "actual": actual,
                "goal_status": s.goal_status,
                "goal_status_display": goal_labels.get(s.goal_status, s.goal_status),
            }))
        return Response(out)


class SavingsDetailView(APIView):
    def get(self, request, year, month):
        uid = user_id(request.user)
        obj = SavingsFS.get_by_user_month(uid, int(year), int(month))
        if not obj:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        report_currency = resolve_report_currency(request.user, request.query_params.get("report_currency"))
        actual = (
            obj.actual if obj.actual is not None
            else savings_actual(request.user, obj.year, obj.month, report_currency=report_currency)
        )
        return Response(decimal_to_json({
            "year": obj.year,
            "month": obj.month,
            "target": obj.target,
            "actual": actual,
            "report_currency": report_currency,
            "goal_status": obj.goal_status,
        }))

    def patch(self, request, year, month):
        uid = user_id(request.user)
        obj = SavingsFS.get_by_user_month(uid, int(year), int(month))
        if not obj:
            obj = SavingsFS(user_id=uid, year=int(year), month=int(month), target=Decimal("0"), goal_status="pending")
        serializer = SavingsSerializer(data={**request.data, "year": year, "month": month})
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        obj.target = cd["target"]
        obj.actual = cd.get("actual")
        obj.goal_status = cd["goal_status"]
        obj.save()
        return Response(decimal_to_json({"target": obj.target, "actual": obj.actual, "goal_status": obj.goal_status}))


class CommitmentListCreateView(APIView):
    def get(self, request):
        uid = user_id(request.user)
        # Opportunistically send due reminders while the user is active
        try:
            evaluate_commitment_reminders(request.user)
        except Exception:
            pass
        items = CommitmentFS.list_by_user(uid)
        seen_ids = set()
        out = []
        for c in items:
            if not c.pk or c.pk in seen_ids:
                continue
            seen_ids.add(c.pk)
            progress = schedule_progress(c)
            out.append(decimal_to_json({
                "id": c.pk,
                "name": c.name,
                "amount": c.amount,
                "start_date": c.start_date.isoformat() if c.start_date else None,
                "term_months": c.term_months,
                "frequency": c.frequency,
                "payment_amount": c.payment_amount,
                "balloon": c.balloon,
                "currency": getattr(c, "currency", None) or "USD",
                "reminder_enabled": c.reminder_enabled,
                "reminder_days_before": c.reminder_days_before,
                "remaining_principal": progress["remaining_principal"],
                "payments_total": progress["payments_total"],
                "payments_completed": progress["payments_completed"],
                "payments_remaining": progress["payments_remaining"],
                "next_due_date": progress["next_due_date"],
                "next_due_amount": progress["next_due_amount"],
                "next_due_line_id": progress.get("next_due_line_id"),
                "upcoming_count": progress["upcoming_count"],
                "overdue_count": progress["overdue_count"],
            }))
        return Response(out)

    def post(self, request):
        serializer = CommitmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        c = CommitmentFS(
            user_id=user_id(request.user),
            name=cd["name"],
            amount=cd["amount"],
            start_date=cd["start_date"],
            term_months=cd["term_months"],
            frequency=cd["frequency"],
            payment_amount=cd["payment_amount"],
            balloon=cd.get("balloon") or Decimal("0"),
            currency=cd.get("currency") or "USD",
            reminder_enabled=cd.get("reminder_enabled", True),
            reminder_days_before=cd.get("reminder_days_before", 3),
        )
        c.save()
        generate_schedule_lines(c, replace=True)
        on_commitment_change(request.user, c.pk, "created", c.name)
        return Response({"id": c.pk}, status=status.HTTP_201_CREATED)


class CommitmentDetailView(APIView):
    def get(self, request, pk):
        c = CommitmentFS.get(pk)
        if not c or c.user_id != user_id(request.user):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        progress = schedule_progress(c)
        lines = progress["lines"]
        # One row per installment in API response
        seen_line_ids = set()
        unique_lines = []
        for l in lines:
            if l.pk and l.pk in seen_line_ids:
                continue
            if l.pk:
                seen_line_ids.add(l.pk)
            unique_lines.append(l)
        return Response(decimal_to_json({
            "id": c.pk,
            "name": c.name,
            "amount": c.amount,
            "start_date": c.start_date.isoformat() if c.start_date else None,
            "term_months": c.term_months,
            "frequency": c.frequency,
            "payment_amount": c.payment_amount,
            "balloon": c.balloon,
            "currency": getattr(c, "currency", None) or "USD",
            "reminder_enabled": c.reminder_enabled,
            "reminder_days_before": c.reminder_days_before,
            "remaining_principal": progress["remaining_principal"],
            "payments_total": progress["payments_total"],
            "payments_completed": progress["payments_completed"],
            "payments_remaining": progress["payments_remaining"],
            "next_due_date": progress["next_due_date"],
            "next_due_amount": progress["next_due_amount"],
            "upcoming_count": progress["upcoming_count"],
            "overdue_count": progress["overdue_count"],
            "schedule": [line_to_dict(l) for l in unique_lines],
        }))

    def patch(self, request, pk):
        c = CommitmentFS.get(pk)
        if not c or c.user_id != user_id(request.user):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CommitmentSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        schedule_fields = {"start_date", "term_months", "frequency", "payment_amount", "balloon"}
        touched_schedule = False
        for field, value in cd.items():
            setattr(c, field, value)
            if field in schedule_fields:
                touched_schedule = True
        c.save()
        # Rebuild outstanding installments; paid ones (and their transactions) are kept.
        if touched_schedule:
            generate_schedule_lines(c, replace=True)
            on_commitment_change(request.user, c.pk, "updated", c.name)
        return Response({"id": c.pk})

    def delete(self, request, pk):
        c = CommitmentFS.get(pk)
        if not c or c.user_id != user_id(request.user):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        CommitmentScheduleLineFS.delete_by_commitment(c.pk)
        c.delete()
        on_commitment_change(request.user, c.pk, "deleted", c.name)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CommitmentScheduleView(APIView):
    def get(self, request, pk):
        c = CommitmentFS.get(pk)
        if not c or c.user_id != user_id(request.user):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        lines = ensure_schedule(c)
        return Response(decimal_to_json([line_to_dict(l) for l in lines]))


class CommitmentSchedulePayView(APIView):
    def post(self, request, pk, line_id):
        c = CommitmentFS.get(pk)
        if not c or c.user_id != user_id(request.user):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        line = CommitmentScheduleLineFS.get(line_id)
        if not line or line.commitment_id != c.pk:
            return Response({"detail": "Schedule line not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = MarkPaymentSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        paid_date = serializer.validated_data.get("paid_date") or date.today()
        uid = user_id(request.user)

        category_id = (request.data.get("category_id") or "").strip() or None
        if category_id:
            sub = _require_subcategory(request.user, category_id)
            if not sub:
                return Response(
                    {"category_id": [_category_id_field_error(request.user, category_id)]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            category_id = sub.pk
        acc = None
        account_id = _parse_account_id(request.data)
        if account_id:
            acc, acc_err = _resolve_account(uid, account_id)
            if acc_err:
                return Response(acc_err, status=status.HTTP_400_BAD_REQUEST)

        # Marking paid always records the expense, so savings stay correct.
        _, txn = record_line_payment(
            request.user, c, line, paid_date, category_id=category_id, account=acc
        )
        trigger_budget_alerts(request.user, paid_date.year, paid_date.month)
        out = line_to_dict(line)
        out["transaction_id"] = txn.pk
        return Response(decimal_to_json(out))


class CommitmentScheduleLineDetailView(APIView):
    """Update due_date / payment_date / amount on a schedule installment."""

    def patch(self, request, pk, line_id):
        c = CommitmentFS.get(pk)
        if not c or c.user_id != user_id(request.user):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        line = CommitmentScheduleLineFS.get(line_id)
        if not line or line.commitment_id != c.pk:
            return Response({"detail": "Schedule line not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ScheduleLineUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        was_paid = line.status == "paid"
        if "due_date" in cd:
            line.due_date = cd["due_date"]
            line.reminder_sent = False
        if "amount" in cd:
            line.amount = cd["amount"]

        target_status = line.status
        target_paid_date = line.paid_date
        if "status" in cd:
            target_status = cd["status"]
            if target_status == "outstanding":
                target_paid_date = None
        if "paid_date" in cd:
            target_paid_date = cd["paid_date"]
            target_status = "paid" if cd["paid_date"] else (
                "outstanding" if target_status == "paid" else target_status
            )

        # Paid <-> outstanding goes through the same flow as pay/unpay (records or
        # removes the expense transaction); other edits keep the transaction in step.
        if target_status == "paid" and not was_paid:
            record_line_payment(request.user, c, line, target_paid_date or date.today())
        elif target_status != "paid" and was_paid:
            reverse_line_payment(request.user, line)
            if line.status != target_status:
                line.status = target_status
                line.save()
        else:
            line.status = target_status
            line.paid_date = target_paid_date
            line.save()
            if line.status == "paid":
                sync_payment_date(request.user, line)
        return Response(decimal_to_json(line_to_dict(line)))


class CommitmentScheduleUnpayView(APIView):
    def post(self, request, pk, line_id):
        c = CommitmentFS.get(pk)
        if not c or c.user_id != user_id(request.user):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        line = CommitmentScheduleLineFS.get(line_id)
        if not line or line.commitment_id != c.pk:
            return Response({"detail": "Schedule line not found."}, status=status.HTTP_404_NOT_FOUND)
        # Removes the linked expense transaction too.
        reverse_line_payment(request.user, line)
        trigger_budget_alerts(request.user)
        return Response(decimal_to_json(line_to_dict(line)))


class CommitmentRegenerateScheduleView(APIView):
    def post(self, request, pk):
        c = CommitmentFS.get(pk)
        if not c or c.user_id != user_id(request.user):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        lines = generate_schedule_lines(c, replace=True)
        on_commitment_change(request.user, c.pk, "updated", c.name)
        return Response(decimal_to_json({
            "id": c.pk,
            "payments_total": len(lines),
            "schedule": [line_to_dict(l) for l in lines],
        }))


class FinancialStandingListCreateView(APIView):
    def get(self, request):
        uid = user_id(request.user)
        items = FinancialStandingFS.list_by_user(uid)
        return Response([
            decimal_to_json({
                "id": s.pk,
                "snapshot_date": s.snapshot_date.isoformat() if s.snapshot_date else None,
                "total_assets": s.total_assets,
                "current_assets": s.current_assets,
                "fixed_assets": s.fixed_assets,
                "total_liabilities": s.total_liabilities,
                "short_term_liabilities": s.short_term_liabilities,
                "long_term_liabilities": s.long_term_liabilities,
                "notes": s.notes,
            })
            for s in items
        ])

    def post(self, request):
        serializer = FinancialStandingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        s = FinancialStandingFS(
            user_id=user_id(request.user),
            snapshot_date=cd["snapshot_date"],
            total_assets=cd.get("total_assets") or Decimal("0"),
            current_assets=cd.get("current_assets") or Decimal("0"),
            fixed_assets=cd.get("fixed_assets") or Decimal("0"),
            total_liabilities=cd.get("total_liabilities") or Decimal("0"),
            short_term_liabilities=cd.get("short_term_liabilities") or Decimal("0"),
            long_term_liabilities=cd.get("long_term_liabilities") or Decimal("0"),
            notes=cd.get("notes") or "",
        )
        s.save()
        return Response({"id": s.pk}, status=status.HTTP_201_CREATED)


class AlertListView(APIView):
    def get(self, request):
        uid = user_id(request.user)
        show = request.query_params.get("show", "open")
        today = date.today()
        year = _query_int(request, "year", today.year)
        month = _query_int(request, "month", today.month)
        refresh = request.query_params.get("refresh", "").lower() in ("1", "true", "yes")
        if refresh:
            refresh_alerts_for_user(request.user, year, month, force=True)
        alerts = BudgetAlertFS.list_by_user(uid, open_only=False, limit=300)
        if show != "all":
            # open = unresolved and not snoozed; snoozed; resolved
            wanted = show if show in ("snoozed", "resolved") else "open"
            alerts = [a for a in alerts if alert_state(a) == wanted]
        return Response([_alert_dict(a) for a in alerts])


def _iso(value):
    return value.isoformat() if value else None


def _alert_dict(a) -> dict:
    return decimal_to_json({
        "id": a.pk,
        "severity": a.severity,
        "title": a.title,
        "description": a.description,
        "alert_type": getattr(a, "alert_type", None) or "utilization",
        "year": a.year,
        "month": a.month,
        "category_id": a.category_id,
        "utilization_pct": a.utilization_pct,
        "actual": a.actual,
        "forecast": a.forecast,
        "is_resolved": a.is_resolved,
        "state": alert_state(a),
        "resolution": getattr(a, "resolution", "") or "",
        "resolved_at": _iso(getattr(a, "resolved_at", None)),
        "snoozed_until": _iso(getattr(a, "snoozed_until", None)) if alert_is_snoozed(a) else None,
        "created_at": _iso(getattr(a, "created_at", None)),
        "commitment_id": getattr(a, "commitment_id", "") or "",
        "schedule_line_id": getattr(a, "schedule_line_id", "") or "",
        "due_date": getattr(a, "due_date", "") or "",
        "commitment_name": getattr(a, "commitment_name", "") or "",
    })


def _snooze_days(data):
    try:
        days = int(data.get("days", 1))
    except (TypeError, ValueError):
        return None
    return days if days in SNOOZE_DAY_CHOICES else None


class AlertResolveView(APIView):
    def post(self, request, pk):
        alert = resolve_alert(request.user, pk)
        if not alert:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"id": alert.pk, "is_resolved": True})


class AlertReopenView(APIView):
    def post(self, request, pk):
        alert = reopen_alert(request.user, pk)
        if not alert:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_alert_dict(alert))


class AlertSnoozeView(APIView):
    """POST {"days": 1|3|7} to snooze; DELETE to unsnooze."""

    def post(self, request, pk):
        days = _snooze_days(request.data)
        if days is None:
            return Response(
                {"days": [f"Choose one of {', '.join(map(str, SNOOZE_DAY_CHOICES))} days."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        alert = snooze_alert(request.user, pk, days)
        if not alert:
            return Response({"detail": "Not found or already resolved."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_alert_dict(alert))

    def delete(self, request, pk):
        alert = unsnooze_alert(request.user, pk)
        if not alert:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(_alert_dict(alert))


class AlertBulkView(APIView):
    """
    POST {"action": "resolve"|"reopen"|"snooze"|"unsnooze", "ids": [...], "days": 1|3|7}
    Applies to the caller's own alerts only; unknown ids are reported, not fatal.
    """

    MAX_IDS = 300

    def post(self, request):
        action = (request.data.get("action") or "").strip()
        ids = request.data.get("ids") or []
        if not isinstance(ids, list) or not ids:
            return Response({"ids": ["Select at least one alert."]}, status=status.HTTP_400_BAD_REQUEST)
        if len(ids) > self.MAX_IDS:
            return Response({"ids": [f"At most {self.MAX_IDS} alerts at once."]}, status=status.HTTP_400_BAD_REQUEST)
        if action == "snooze":
            days = _snooze_days(request.data)
            if days is None:
                return Response(
                    {"days": [f"Choose one of {', '.join(map(str, SNOOZE_DAY_CHOICES))} days."]},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            apply = lambda pk: snooze_alert(request.user, pk, days)  # noqa: E731
        elif action == "resolve":
            apply = lambda pk: resolve_alert(request.user, pk)  # noqa: E731
        elif action == "reopen":
            apply = lambda pk: reopen_alert(request.user, pk)  # noqa: E731
        elif action == "unsnooze":
            apply = lambda pk: unsnooze_alert(request.user, pk)  # noqa: E731
        else:
            return Response(
                {"action": ["Use resolve, reopen, snooze or unsnooze."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        updated, failed = [], []
        for pk in dict.fromkeys(str(i) for i in ids):
            (updated if apply(pk) else failed).append(pk)
        return Response({"action": action, "updated": updated, "failed": failed})


class AlertRecordCommitmentView(APIView):
    """
    From a commitment due-date alert: optionally record an expense transaction
    (included in utilization) and mark the installment paid.
    """

    def post(self, request, pk):
        uid = user_id(request.user)
        alert = BudgetAlertFS.get(pk)
        if not alert or alert.user_id != uid:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        if alert.is_resolved:
            return Response({"detail": "Alert already resolved."}, status=status.HTTP_400_BAD_REQUEST)

        record_expense = request.data.get("record_expense", True)
        if record_expense in (False, "false", "0", 0):
            resolve_alert(request.user, pk)
            return Response({"id": pk, "recorded": False, "is_resolved": True})

        category_id = (request.data.get("category_id") or "").strip()
        if not category_id:
            return Response(
                {"category_id": ["Category is required to add to expenses and utilization."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        sub = _require_subcategory(request.user, category_id)
        if not sub:
            return Response(
                {"category_id": [_category_id_field_error(request.user, category_id)]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        category_id = sub.pk

        # Account is optional here (older clients don't send it).
        acc = None
        account_id = _parse_account_id(request.data)
        if account_id:
            acc, acc_err = _resolve_account(uid, account_id)
            if acc_err:
                return Response(acc_err, status=status.HTTP_400_BAD_REQUEST)

        commitment_id = (getattr(alert, "commitment_id", "") or "").strip()
        schedule_line_id = (getattr(alert, "schedule_line_id", "") or "").strip()
        if not commitment_id and str(alert.category_id or "").startswith("commitment:"):
            commitment_id = alert.category_id.split(":", 1)[1]
        if not schedule_line_id and alert.fingerprint:
            parts = str(alert.fingerprint).split("|")
            if len(parts) >= 3 and parts[1] == "due":
                schedule_line_id = parts[2]

        if not commitment_id or not schedule_line_id:
            return Response(
                {"detail": "Alert is missing commitment installment details."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        c = CommitmentFS.get(commitment_id)
        if not c or c.user_id != uid:
            return Response({"commitment_id": ["Commitment not found."]}, status=status.HTTP_400_BAD_REQUEST)

        progress = schedule_progress(c)
        paid_line = next(
            (l for l in progress["lines"] if l.pk == schedule_line_id and l.status == "outstanding"),
            None,
        )
        if not paid_line:
            return Response(
                {"commitment_id": ["This installment is no longer outstanding."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        ext_id = f"commitment_line:{schedule_line_id}"
        if TransactionFS.exists_by_external_id(uid, ext_id):
            resolve_alert(request.user, pk)
            return Response(
                {"detail": "Transaction already recorded for this installment.", "recorded": False},
                status=status.HTTP_409_CONFLICT,
            )

        due_raw = (getattr(alert, "due_date", "") or "").strip()
        payment_raw = (request.data.get("payment_date") or "").strip()
        if payment_raw:
            try:
                txn_date = date.fromisoformat(payment_raw[:10])
            except ValueError:
                txn_date = date.today()
        else:
            # Payment recorded now — use today so it appears in current month lists
            txn_date = date.today()
        amount = paid_line.amount
        name = (getattr(alert, "commitment_name", "") or c.name or "Commitment").strip()

        t = TransactionFS(
            user_id=uid,
            date=txn_date,
            month=get_month_str(txn_date),
            description=name[:500],
            category_id=category_id,
            classification=None,
            amount=amount,
            currency=getattr(c, "currency", None) or "USD",
            note=f"Commitment payment — {name}",
            time=datetime.now().strftime("%H:%M"),
            direction="expense",
            source_account=acc.name if acc else "",
            income_source_id=acc.pk if acc else "",
            commitment_id=commitment_id,
            schedule_line_id=schedule_line_id,
            external_id=ext_id,
            include_in_utilization=True,
        )
        t.save()
        mark_line_paid(paid_line, txn_date)
        refresh_alerts_for_user(request.user, txn_date.year, txn_date.month, force=True)
        resolve_alert(request.user, pk)
        return Response(
            {
                "id": t.pk,
                "recorded": True,
                "transaction": transaction_to_dict(t),
                "alert_id": pk,
                "is_resolved": True,
            },
            status=status.HTTP_201_CREATED,
        )


class AlertCountView(APIView):
    def get(self, request):
        # "count" stays the badge number (open, not snoozed); the rest feed the alert tabs.
        counts = alert_counts(request.user)
        return Response({"count": counts["open"], **counts})


class AccountListCreateView(APIView):
    """User financial accounts (bank, card, wallet) used on transactions."""

    def get(self, request):
        uid = user_id(request.user)
        active_only = request.query_params.get("active") == "1"
        rows = IncomeSourceFS.list_by_user(uid, active_only=active_only)
        return Response([_account_to_dict(s) for s in rows])

    def post(self, request):
        serializer = IncomeSourceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        name = cd["name"].strip()
        if not name:
            return Response({"name": ["Name is required."]}, status=status.HTTP_400_BAD_REQUEST)
        uid = user_id(request.user)
        clash = [s for s in IncomeSourceFS.list_by_user(uid) if s.name.lower() == name.lower()]
        if clash:
            return Response({"name": ["An account with this name already exists."]}, status=status.HTTP_400_BAD_REQUEST)
        s = IncomeSourceFS(
            user_id=uid,
            name=name,
            account_type=cd.get("account_type", "bank"),
            order=cd.get("order", 0),
            is_active=cd.get("is_active", True),
            is_default_for_expenses=cd.get("is_default_for_expenses", False),
        )
        if s.is_default_for_expenses:
            _clear_expense_default_accounts(uid)
        elif not any(getattr(a, "is_default_for_expenses", False) for a in IncomeSourceFS.list_by_user(uid)):
            s.is_default_for_expenses = True
        s.save()
        return Response(_account_to_dict(s), status=status.HTTP_201_CREATED)


class AccountDetailView(APIView):
    def patch(self, request, pk):
        uid = user_id(request.user)
        s = IncomeSourceFS.get(pk)
        if not s or s.user_id != uid:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = IncomeSourceSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        if "name" in cd:
            name = cd["name"].strip()
            if not name:
                return Response({"name": ["Name is required."]}, status=status.HTTP_400_BAD_REQUEST)
            clash = [
                x for x in IncomeSourceFS.list_by_user(uid)
                if x.pk != pk and x.name.lower() == name.lower()
            ]
            if clash:
                return Response({"name": ["An account with this name already exists."]}, status=status.HTTP_400_BAD_REQUEST)
            s.name = name
        if "account_type" in cd:
            s.account_type = cd["account_type"]
        if "order" in cd:
            s.order = cd["order"]
        if "is_active" in cd:
            s.is_active = cd["is_active"]
            if not s.is_active:
                s.is_default_for_expenses = False
        if "is_default_for_expenses" in cd:
            s.is_default_for_expenses = bool(cd["is_default_for_expenses"])
            if s.is_default_for_expenses:
                _clear_expense_default_accounts(uid, except_pk=pk)
        s.save()
        return Response(_account_to_dict(s))

    def delete(self, request, pk):
        uid = user_id(request.user)
        s = IncomeSourceFS.get(pk)
        if not s or s.user_id != uid:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        s.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# Backward-compatible aliases
IncomeSourceListCreateView = AccountListCreateView
IncomeSourceDetailView = AccountDetailView


class MerchantLinkListCreateView(APIView):
    def get(self, request):
        uid = user_id(request.user)
        links = MerchantCategoryLinkFS.list_by_user(uid)
        groups_list, categories_by_id = categories_and_groups_for_user(request.user)
        groups = {g.pk: g for g in groups_list}
        return Response([_merchant_link_dict(l, categories_by_id, groups) for l in links])

    def post(self, request):
        serializer = MerchantLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        uid = user_id(request.user)
        keyword = cd["keyword"].strip()
        category_id = cd["category_id"]
        cat = _require_subcategory(request.user, category_id)
        if not cat:
            return Response(
                {"category_id": [_category_id_field_error(request.user, category_id)]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Upsert: if same keyword exists for user, update category
        existing = next(
            (l for l in MerchantCategoryLinkFS.list_by_user(uid) if l.keyword.lower() == keyword.lower()),
            None,
        )
        if existing:
            existing.category_id = category_id
            existing.keyword = keyword
            existing.save()
            link = existing
            created = False
        else:
            link = MerchantCategoryLinkFS(keyword=keyword, category_id=category_id, user_id=uid)
            link.save()
            created = True

        updated = 0
        if cd.get("apply_unmatched", True):
            updated = apply_merchant_link_to_transactions(
                request.user,
                keyword,
                category_id,
                transaction_ids=cd.get("transaction_ids") or None,
            )
            trigger_budget_alerts(request.user)

        return Response(
            {"id": link.pk, "created": created, "transactions_updated": updated},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class MerchantLinkDetailView(APIView):
    def delete(self, request, pk):
        uid = user_id(request.user)
        link = MerchantCategoryLinkFS.get(pk)
        if not link or link.user_id != uid:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        link.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class TypeMapListView(APIView):
    def get(self, request):
        uid = user_id(request.user)
        effective = TypeCategoryMapFS.get_map_for_user(uid)
        categories = {c.pk: c for c in visible_categories(request.user)}
        groups = {g.pk: g for g in visible_groups(request.user)}
        return Response([
            {
                "consumption_type": ctype,
                "category_id": effective.get(ctype, ""),
                "category_name": (
                    categories[effective[ctype]].name
                    if effective.get(ctype) in categories
                    else ""
                ),
                "group_id": (
                    categories[effective[ctype]].group_id
                    if effective.get(ctype) in categories
                    else ""
                ),
                "group_name": (
                    groups.get(categories[effective[ctype]].group_id).name
                    if effective.get(ctype) in categories
                    and categories[effective[ctype]].group_id in groups
                    else ""
                ),
            }
            for ctype in CONSUMPTION_TYPES
        ])

    def post(self, request):
        serializer = TypeCategoryMapSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        cat = get_visible_category(request.user, cd["category_id"])
        if not cat:
            return Response({"category_id": ["Subcategory not found."]}, status=status.HTTP_400_BAD_REQUEST)
        uid = user_id(request.user)
        existing = next((m for m in TypeCategoryMapFS.list_by_user(uid) if m.consumption_type == cd["consumption_type"]), None)
        if existing:
            existing.category_id = cd["category_id"]
            existing.save()
            return Response({"id": existing.pk})
        m = TypeCategoryMapFS(user_id=uid, consumption_type=cd["consumption_type"], category_id=cd["category_id"])
        m.save()
        return Response({"id": m.pk}, status=status.HTTP_201_CREATED)


class ThresholdListCreateView(APIView):
    def get(self, request):
        uid = user_id(request.user)
        thresholds = BudgetThresholdFS.list_by_user(uid)
        categories = {c.pk: c for c in visible_categories(request.user)}
        return Response([
            decimal_to_json({
                "id": t.pk,
                "category_id": t.category_id,
                "category_name": categories.get(t.category_id).name if t.category_id and t.category_id in categories else "Global default",
                "warn_pct": t.warn_pct,
                "critical_pct": t.critical_pct,
                "email_enabled": t.email_enabled,
            })
            for t in thresholds
        ])

    def post(self, request):
        serializer = BudgetThresholdSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cd = serializer.validated_data
        uid = user_id(request.user)
        cat_id = (cd.get("category_id") or "").strip() or None
        # Exact match only: get_for_category falls back to the global row, which would
        # make a new category threshold overwrite the global default.
        existing = next(
            (t for t in BudgetThresholdFS.list_by_user(uid) if (t.category_id or None) == cat_id),
            None,
        )
        if existing:
            existing.warn_pct = cd["warn_pct"]
            existing.critical_pct = cd["critical_pct"]
            existing.email_enabled = cd.get("email_enabled", True)
            existing.save()
            return Response({"id": existing.pk})
        t = BudgetThresholdFS(
            user_id=uid,
            category_id=cat_id,
            warn_pct=cd["warn_pct"],
            critical_pct=cd["critical_pct"],
            email_enabled=cd.get("email_enabled", True),
        )
        t.save()
        return Response({"id": t.pk}, status=status.HTTP_201_CREATED)


class ThresholdDeleteView(APIView):
    def delete(self, request, pk):
        uid = user_id(request.user)
        t = BudgetThresholdFS.get(pk)
        if not t or t.user_id != uid:
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        t.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
