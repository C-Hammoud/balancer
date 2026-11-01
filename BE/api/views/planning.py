"""Budget planning API: income streams, needs/wants buckets, plan suggestions, notifications."""
from datetime import date
from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.currency import resolve_report_currency
from api.locale_defaults import VALID_CURRENCIES
from api.user_profile import get_user_profile
from api.utils import decimal_to_json, user_id
from budgeting import planning
from budgeting.store import BudgetPlanFS, GroupBucketFS, IncomeSourceFS, IncomeStreamFS, NotificationFS

FREQUENCIES = ("monthly", "biweekly", "weekly", "yearly")


def _not_found():
    return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


def _owned(adapter, request, pk):
    obj = adapter.get(pk)
    return obj if obj and obj.user_id == user_id(request.user) else None


def _year_month(data):
    today = date.today()
    try:
        year = int(data.get("year") or today.year)
        month = int(data.get("month") or today.month)
    except (TypeError, ValueError):
        return None
    return (year, month) if 2000 <= year <= 2100 and 1 <= month <= 12 else None


# ---- Income streams ---------------------------------------------------------

def _stream_dict(s) -> dict:
    return decimal_to_json({
        "id": s.pk,
        "name": s.name,
        "amount": s.amount,
        "currency": s.currency,
        "frequency": s.frequency,
        "monthly_amount": planning.stream_monthly_amount(s).quantize(Decimal("0.01")),
        "account_id": s.account_id or "",
        "is_active": s.is_active,
    })


def _apply_stream(s, data, request, partial=False):
    """Validate and copy fields onto the stream. Returns an error dict or None."""
    errors = {}
    if "name" in data or not partial:
        name = (data.get("name") or "").strip()
        if not name:
            errors["name"] = ["Name is required (e.g. Salary)."]
        s.name = name[:120]
    if "amount" in data or not partial:
        try:
            amount = Decimal(str(data.get("amount")))
            if amount <= 0:
                raise InvalidOperation
            s.amount = amount
        except (InvalidOperation, TypeError, ValueError):
            errors["amount"] = ["Enter an amount greater than zero."]
    if "currency" in data or not partial:
        cur = (data.get("currency") or s.currency or "USD").strip().upper()
        if cur not in VALID_CURRENCIES:
            errors["currency"] = ["Unsupported currency."]
        s.currency = cur
    if "frequency" in data:
        if data["frequency"] not in FREQUENCIES:
            errors["frequency"] = ["Use monthly, biweekly, weekly or yearly."]
        s.frequency = data["frequency"]
    if "account_id" in data:
        acc_id = (data.get("account_id") or "").strip()
        acc = IncomeSourceFS.get(acc_id) if acc_id else None
        if acc_id and (not acc or acc.user_id != user_id(request.user)):
            errors["account_id"] = ["Account not found."]
        s.account_id = acc_id
    if "is_active" in data:
        s.is_active = bool(data["is_active"])
    return errors or None


class IncomeStreamListCreateView(APIView):
    def get(self, request):
        rows = IncomeStreamFS.list_by_user(user_id(request.user))
        currency = resolve_report_currency(request.user, request.query_params.get("currency"))
        return Response({
            "streams": [_stream_dict(s) for s in rows],
            "currency": currency,
            "monthly_total": str(planning.money_round(planning.expected_income(request.user, currency), currency)),
        })

    def post(self, request):
        s = IncomeStreamFS(user_id=user_id(request.user))
        errors = _apply_stream(s, request.data, request)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        s.save()
        return Response(_stream_dict(s), status=status.HTTP_201_CREATED)


class IncomeStreamDetailView(APIView):
    def patch(self, request, pk):
        s = _owned(IncomeStreamFS, request, pk)
        if not s:
            return _not_found()
        errors = _apply_stream(s, request.data, request, partial=True)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        s.save()
        return Response(_stream_dict(s))

    def delete(self, request, pk):
        s = _owned(IncomeStreamFS, request, pk)
        if not s:
            return _not_found()
        s.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---- Needs / wants buckets -------------------------------------------------

class PlanBucketsView(APIView):
    def get(self, request):
        groups = planning.plannable_groups(request.user)
        saved = {b.group_id for b in GroupBucketFS.list_by_user(user_id(request.user))}
        buckets = planning.group_buckets(request.user, groups)
        return Response([
            {"group_id": g.pk, "group_name": g.name, "bucket": buckets[g.pk], "is_default": g.pk not in saved}
            for g in groups
        ])

    def put(self, request):
        wanted = request.data.get("buckets") or {}
        if not isinstance(wanted, dict):
            return Response({"buckets": ["Send {group_id: bucket}."]}, status=status.HTTP_400_BAD_REQUEST)
        visible = {g.pk for g in planning.plannable_groups(request.user)}
        uid = user_id(request.user)
        existing = {b.group_id: b for b in GroupBucketFS.list_by_user(uid)}
        for gid, bucket in wanted.items():
            if gid not in visible or bucket not in planning.BUCKETS:
                return Response({"buckets": [f"Invalid group or bucket: {gid}"]}, status=status.HTTP_400_BAD_REQUEST)
            row = existing.get(gid) or GroupBucketFS(user_id=uid, group_id=gid)
            row.bucket = bucket
            row.save()
        return self.get(request)


# ---- Plans ------------------------------------------------------------------

def _plan_settings(request, data):
    ym = _year_month(data)
    currency = resolve_report_currency(request.user, data.get("currency"))
    return ym, currency, int(get_user_profile(request.user).savings_target_pct)


class PlanPreviewView(APIView):
    """Both plan types side by side for a month; nothing is saved."""

    def post(self, request):
        ym, currency, pct = _plan_settings(request, request.data)
        if not ym:
            return Response({"detail": "Invalid year or month."}, status=status.HTTP_400_BAD_REQUEST)
        plans = [planning.build_plan(request.user, *ym, t, currency, savings_pct=pct) for t in planning.PLAN_TYPES]
        return Response(decimal_to_json({"year": ym[0], "month": ym[1], "currency": currency, "plans": plans}))


class PlanListCreateView(APIView):
    def get(self, request):
        uid = user_id(request.user)
        ym = _year_month(request.query_params) if request.query_params.get("month") else None
        rows = BudgetPlanFS.list_for_month(uid, *ym) if ym else BudgetPlanFS.list_by_user(uid, limit=50)
        status_filter = request.query_params.get("status")
        if status_filter:
            rows = [p for p in rows if p.status == status_filter]
        return Response(decimal_to_json([planning.plan_to_dict(p) for p in rows]))

    def post(self, request):
        """Save a suggestion: {year, month, plan_type} (computed now) for the user to review."""
        ym, currency, pct = _plan_settings(request, request.data)
        plan_type = request.data.get("plan_type") or "rule_50_30_20"
        if not ym:
            return Response({"detail": "Invalid year or month."}, status=status.HTTP_400_BAD_REQUEST)
        if plan_type not in planning.PLAN_TYPES:
            return Response({"plan_type": ["Unknown plan type."]}, status=status.HTTP_400_BAD_REQUEST)
        plan = planning.build_plan(request.user, *ym, plan_type, currency, savings_pct=pct)
        obj = planning.save_plan(request.user, plan, reason="manual")
        return Response(decimal_to_json(planning.plan_to_dict(obj)), status=status.HTTP_201_CREATED)


class PlanDetailView(APIView):
    def get(self, request, pk):
        obj = _owned(BudgetPlanFS, request, pk)
        return Response(decimal_to_json(planning.plan_to_dict(obj))) if obj else _not_found()

    def patch(self, request, pk):
        """Edit line amounts: {"amounts": {group_id: amount}}."""
        obj = _owned(BudgetPlanFS, request, pk)
        if not obj:
            return _not_found()
        amounts = request.data.get("amounts") or {}
        if not isinstance(amounts, dict):
            return Response({"amounts": ["Send {group_id: amount}."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            obj = planning.update_plan_lines(obj, amounts)
        except (ValueError, InvalidOperation) as exc:
            return Response({"detail": str(exc) or "Invalid amount."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(decimal_to_json(planning.plan_to_dict(obj)))


class PlanAcceptView(APIView):
    def post(self, request, pk):
        obj = _owned(BudgetPlanFS, request, pk)
        if not obj:
            return _not_found()
        try:
            planning.accept_plan(request.user, obj)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(decimal_to_json(planning.plan_to_dict(obj)))


class PlanDismissView(APIView):
    def post(self, request, pk):
        obj = _owned(BudgetPlanFS, request, pk)
        if not obj:
            return _not_found()
        if obj.status == "suggested":
            obj.status = "dismissed"
            obj.save()
        return Response(decimal_to_json(planning.plan_to_dict(obj)))


# ---- Notifications ----------------------------------------------------------

def _notification_dict(n) -> dict:
    return {
        "id": n.pk,
        "kind": n.kind,
        "title": n.title,
        "body": n.body,
        "link": n.link,
        "related_id": n.related_id,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


class NotificationListView(APIView):
    def get(self, request):
        rows = NotificationFS.list_by_user(user_id(request.user), limit=100)
        if request.query_params.get("unread") in ("1", "true"):
            rows = [n for n in rows if not n.is_read]
        return Response([_notification_dict(n) for n in rows])


class NotificationCountView(APIView):
    def get(self, request):
        rows = NotificationFS.list_by_user(user_id(request.user), limit=500)
        return Response({"unread": sum(1 for n in rows if not n.is_read)})


class NotificationReadView(APIView):
    def post(self, request, pk):
        n = _owned(NotificationFS, request, pk)
        if not n:
            return _not_found()
        if not n.is_read:
            n.is_read = True
            n.save()
        return Response(_notification_dict(n))


class NotificationReadAllView(APIView):
    def post(self, request):
        count = 0
        for n in NotificationFS.list_by_user(user_id(request.user), limit=500):
            if not n.is_read:
                n.is_read = True
                n.save()
                count += 1
        return Response({"marked": count})
