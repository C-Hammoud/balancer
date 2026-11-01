"""Risk management API: risk report, history, settings, planned items and account balances."""
from datetime import date
from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from api.currency import resolve_report_currency
from api.locale_defaults import VALID_CURRENCIES
from api.utils import decimal_to_json, user_id
from budgeting import planned, risk
from budgeting.alerts import evaluate_risk_alerts
from budgeting.balances import liquid_and_card_totals
from budgeting.store import IncomeSourceFS, PlannedItemFS, RiskSettingsFS
from budgeting.store.planning_sqlite import RISK_SETTING_FIELDS


def _not_found():
    return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


# ---- Account balances -------------------------------------------------------

class AccountBalancesView(APIView):
    """Per-account balances over all transactions, by currency and converted to report_currency."""

    def get(self, request):
        currency = resolve_report_currency(request.user, request.query_params.get("report_currency"))
        totals = liquid_and_card_totals(request.user, currency)
        return Response(decimal_to_json({
            "currency": currency,
            "accounts": totals["accounts"],
            # Money recorded without an account (or on a deleted one).
            "unassigned": totals["unassigned"],
        }))


# ---- Planned items ----------------------------------------------------------

def _parse_date(value, field, errors, required=False):
    if value in (None, ""):
        if required:
            errors[field] = ["Enter a date (YYYY-MM-DD)."]
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        errors[field] = ["Date has wrong format. Use one of these formats instead: YYYY-MM-DD."]
        return None


def _apply_item(item, data, request, partial=False):
    """Validate and copy fields onto the planned item. Returns an error dict or None."""
    errors = {}
    uid = user_id(request.user)
    if "name" in data or not partial:
        name = (data.get("name") or "").strip()
        if not name:
            errors["name"] = ["Name is required (e.g. Rent)."]
        item.name = name[:120]
    if "kind" in data or not partial:
        kind = data.get("kind") or "expense"
        if kind not in planned.KINDS:
            errors["kind"] = ["Use income or expense."]
        item.kind = kind
    if "amount" in data or not partial:
        try:
            amount = Decimal(str(data.get("amount")).strip())
            if not amount.is_finite() or amount <= 0:
                raise InvalidOperation
            item.amount = amount
        except (InvalidOperation, TypeError, ValueError):
            errors["amount"] = ["Enter an amount greater than zero."]
    if "currency" in data or not partial:
        cur = (data.get("currency") or item.currency or "USD").strip().upper()
        if cur not in VALID_CURRENCIES:
            errors["currency"] = ["Unsupported currency."]
        item.currency = cur
    if "frequency" in data or not partial:
        freq = data.get("frequency") or "monthly"
        if freq not in planned.FREQUENCIES:
            errors["frequency"] = ["Use once, weekly, biweekly, monthly or yearly."]
        item.frequency = freq
    if "start_date" in data or not partial:
        item.start_date = _parse_date(data.get("start_date"), "start_date", errors, required=True)
    if "end_date" in data:
        item.end_date = _parse_date(data.get("end_date"), "end_date", errors)
    if item.start_date and item.end_date and item.end_date < item.start_date:
        errors["end_date"] = ["End date must be on or after the start date."]
    if "account_id" in data:
        acc_id = (data.get("account_id") or "").strip()
        acc = IncomeSourceFS.get(acc_id) if acc_id else None
        if acc_id and (not acc or acc.user_id != uid):
            errors["account_id"] = ["Account not found."]
        item.account_id = acc_id
    if "category_id" in data:
        item.category_id = (data.get("category_id") or "").strip()[:64]
    for flag in ("is_essential", "is_active"):
        if flag in data:
            setattr(item, flag, data[flag] in (True, "true", "1", 1))
    return errors or None


def _owned_item(request, pk):
    item = PlannedItemFS.get(pk)
    return item if item and item.user_id == user_id(request.user) else None


class PlannedItemListCreateView(APIView):
    def get(self, request):
        rows = PlannedItemFS.list_by_user(user_id(request.user), limit=1000)
        kind = request.query_params.get("kind")
        if kind in planned.KINDS:
            rows = [r for r in rows if r.kind == kind]
        currency = resolve_report_currency(request.user, request.query_params.get("currency"))
        recurring = [r for r in rows if r.is_active and r.frequency != "once"]
        income = planned.recurring_monthly_total([r for r in recurring if r.kind == "income"], currency)
        expense = planned.recurring_monthly_total([r for r in recurring if r.kind == "expense"], currency)
        return Response({
            "items": [planned.item_to_dict(r) for r in rows],
            "currency": currency,
            "monthly_income": str(income.quantize(Decimal("0.01"))),
            "monthly_expense": str(expense.quantize(Decimal("0.01"))),
        })

    def post(self, request):
        item = PlannedItemFS(user_id=user_id(request.user))
        errors = _apply_item(item, request.data, request)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        item.save()
        return Response(planned.item_to_dict(item), status=status.HTTP_201_CREATED)


class PlannedItemDetailView(APIView):
    def get(self, request, pk):
        item = _owned_item(request, pk)
        return Response(planned.item_to_dict(item)) if item else _not_found()

    def patch(self, request, pk):
        item = _owned_item(request, pk)
        if not item:
            return _not_found()
        errors = _apply_item(item, request.data, request, partial=True)
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        item.save()
        return Response(planned.item_to_dict(item))

    def delete(self, request, pk):
        item = _owned_item(request, pk)
        if not item:
            return _not_found()
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---- Risk report ------------------------------------------------------------

class RiskReportView(APIView):
    """GET ?refresh=1 also re-evaluates the risk alerts right away."""

    def get(self, request):
        currency = resolve_report_currency(request.user, request.query_params.get("report_currency"))
        report = risk.build_report(request.user, currency)
        if request.query_params.get("refresh", "").lower() in ("1", "true", "yes"):
            evaluate_risk_alerts(request.user, report)
        return Response(report)


class RiskHistoryView(APIView):
    def get(self, request):
        try:
            days = int(request.query_params.get("days", 90))
        except ValueError:
            return Response({"days": ["Enter a number of days."]}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"days": days, "points": risk.history(request.user, days)})


# ---- Risk settings ----------------------------------------------------------

THRESHOLD_PAIRS = (("dti_warn", "dti_high"), ("balloon_warn", "balloon_high"), ("debt_assets_warn", "debt_assets_high"))
DECIMAL_FIELDS = [k for k, kind in RISK_SETTING_FIELDS.items() if kind == "decn"]


def _settings_dict(user, obj) -> dict:
    effective = risk.resolve_thresholds(obj)
    out = {
        "overrides": {k: (None if obj is None or getattr(obj, k) is None else str(getattr(obj, k)))
                      for k in DECIMAL_FIELDS + ["horizon_months"]},
        "effective": {k: str(v) for k, v in effective.items()},
        "defaults": {**{k: str(v) for k, v in risk.DEFAULTS.items()}, "horizon_months": str(risk.DEFAULT_HORIZON_MONTHS)},
        "included_account_ids": list(getattr(obj, "included_account_ids", None) or []),
        "alerts_enabled": True if obj is None else bool(obj.alerts_enabled),
        "email_enabled": True if obj is None else bool(obj.email_enabled),
    }
    return out


class RiskSettingsView(APIView):
    def get(self, request):
        return Response(_settings_dict(request.user, risk.get_settings(request.user)))

    def patch(self, request):
        uid = user_id(request.user)
        obj = risk.get_settings(request.user) or RiskSettingsFS(user_id=uid)
        data = request.data
        errors = {}
        for key in DECIMAL_FIELDS:
            if key not in data:
                continue
            raw = data.get(key)
            if raw in (None, ""):
                setattr(obj, key, None)
                continue
            try:
                value = Decimal(str(raw).strip())
                if not value.is_finite() or value < 0 or value > 1000:
                    raise InvalidOperation
                setattr(obj, key, value)
            except (InvalidOperation, TypeError, ValueError):
                errors[key] = ["Enter a number between 0 and 1000."]
        if "horizon_months" in data:
            raw = data.get("horizon_months")
            if raw in (None, ""):
                obj.horizon_months = None
            else:
                try:
                    months = int(raw)
                    if not 1 <= months <= 24:
                        raise ValueError
                    obj.horizon_months = months
                except (TypeError, ValueError):
                    errors["horizon_months"] = ["Enter a number of months between 1 and 24."]
        if "included_account_ids" in data:
            ids = data.get("included_account_ids") or []
            if not isinstance(ids, list):
                errors["included_account_ids"] = ["Send a list of account ids."]
            else:
                owned = {a.pk for a in IncomeSourceFS.list_by_user(uid)}
                unknown = [i for i in ids if str(i) not in owned]
                if unknown:
                    errors["included_account_ids"] = ["Account not found."]
                obj.included_account_ids = [str(i) for i in ids]
        for flag in ("alerts_enabled", "email_enabled"):
            if flag in data:
                setattr(obj, flag, data[flag] in (True, "true", "1", 1))
        if not errors:
            effective = risk.resolve_thresholds(obj)
            for warn, high in THRESHOLD_PAIRS:
                if effective[warn] > effective[high]:
                    errors[warn] = ["Warning level must be at or below the high level."]
            if effective["emergency_warn_months"] < effective["emergency_high_months"]:
                errors["emergency_warn_months"] = ["Warning months must be at or above the high-risk months."]
        if errors:
            return Response(errors, status=status.HTTP_400_BAD_REQUEST)
        obj.save()
        try:
            evaluate_risk_alerts(request.user)
        except Exception:
            pass
        return Response(_settings_dict(request.user, obj))
