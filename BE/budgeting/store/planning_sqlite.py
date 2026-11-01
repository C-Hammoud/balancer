"""
Django ORM adapters for budget planning (income streams, group buckets, plans, notifications).
Same interface as budgeting/planning_fs.py (Firestore). Fields are declared once in FIELDS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar, Dict, List, Optional, Type

from django.db import models

from budgeting.models import BudgetPlan, GroupBucket, IncomeStream, Notification


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v if v is not None else "0"))
    except Exception:
        return Decimal("0")


class _OrmAdapter:
    _model: ClassVar[Type[models.Model]]
    # field name -> kind: str | int | bool | dec | decn (nullable decimal) | json | dt | date
    FIELDS: ClassVar[Dict[str, str]] = {}

    @classmethod
    def from_model(cls, obj):
        o = cls(pk=str(obj.pk), user_id=str(obj.user_id))
        for name in cls.FIELDS:
            setattr(o, name, getattr(obj, name))
        if hasattr(obj, "created_at"):
            o.created_at = obj.created_at
        return o

    def save(self):
        obj = self._model.objects.get(pk=int(self.pk)) if self.pk else self._model()
        obj.user_id = int(self.user_id)
        for name, kind in self.FIELDS.items():
            value = getattr(self, name)
            if kind == "dec":
                value = _dec(value)
            elif kind == "decn":
                value = None if value is None or value == "" else _dec(value)
            setattr(obj, name, value)
        obj.save()
        self.pk = str(obj.pk)
        if hasattr(obj, "created_at"):
            self.created_at = obj.created_at
        return self

    def delete(self):
        if self.pk:
            self._model.objects.filter(pk=int(self.pk)).delete()

    @classmethod
    def get(cls, pk):
        try:
            return cls.from_model(cls._model.objects.get(pk=int(pk)))
        except (cls._model.DoesNotExist, TypeError, ValueError):
            return None

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 500, **filters) -> List:
        qs = cls._model.objects.filter(user_id=int(user_id), **filters)
        return [cls.from_model(o) for o in qs[:limit]]


@dataclass
class IncomeStreamFS(_OrmAdapter):
    _model: ClassVar = IncomeStream
    FIELDS: ClassVar = {"name": "str", "amount": "dec", "currency": "str", "frequency": "str",
                        "account_id": "str", "is_active": "bool"}
    pk: Optional[str] = None
    user_id: str = ""
    name: str = ""
    amount: Decimal = Decimal("0")
    currency: str = "USD"
    frequency: str = "monthly"
    account_id: str = ""
    is_active: bool = True
    created_at: Optional[datetime] = None


@dataclass
class GroupBucketFS(_OrmAdapter):
    _model: ClassVar = GroupBucket
    FIELDS: ClassVar = {"group_id": "str", "bucket": "str"}
    pk: Optional[str] = None
    user_id: str = ""
    group_id: str = ""
    bucket: str = "wants"


@dataclass
class BudgetPlanFS(_OrmAdapter):
    _model: ClassVar = BudgetPlan
    FIELDS: ClassVar = {
        "year": "int", "month": "int", "plan_type": "str", "status": "str", "reason": "str",
        "currency": "str", "income_total": "dec", "commitments_total": "dec", "available": "dec",
        "needs_total": "dec", "wants_total": "dec", "savings_amount": "dec",
        "lines": "json", "warnings": "json", "accepted_at": "dt",
        "sub_budgets": "json", "reserved_total": "dec",
    }
    pk: Optional[str] = None
    user_id: str = ""
    year: int = 0
    month: int = 0
    plan_type: str = ""
    status: str = "suggested"
    reason: str = "manual"
    currency: str = "USD"
    income_total: Decimal = Decimal("0")
    commitments_total: Decimal = Decimal("0")
    available: Decimal = Decimal("0")
    needs_total: Decimal = Decimal("0")
    wants_total: Decimal = Decimal("0")
    savings_amount: Decimal = Decimal("0")
    lines: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    sub_budgets: List[Dict[str, Any]] = field(default_factory=list)
    reserved_total: Decimal = Decimal("0")
    accepted_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    @classmethod
    def list_for_month(cls, user_id: str, year: int, month: int) -> List:
        return cls.list_by_user(user_id, year=int(year), month=int(month))


@dataclass
class NotificationFS(_OrmAdapter):
    _model: ClassVar = Notification
    FIELDS: ClassVar = {"kind": "str", "title": "str", "body": "str", "link": "str",
                        "related_id": "str", "fingerprint": "str", "is_read": "bool"}
    pk: Optional[str] = None
    user_id: str = ""
    kind: str = ""
    title: str = ""
    body: str = ""
    link: str = ""
    related_id: str = ""
    fingerprint: str = ""
    is_read: bool = False
    created_at: Optional[datetime] = None

    @classmethod
    def exists_fingerprint(cls, user_id: str, fingerprint: str) -> bool:
        return Notification.objects.filter(user_id=int(user_id), fingerprint=fingerprint).exists()


# --- Risk management ---------------------------------------------------------

from datetime import date  # noqa: E402

from budgeting.models import PlannedItem, RiskSettings, RiskSnapshot  # noqa: E402


@dataclass
class PlannedItemFS(_OrmAdapter):
    _model: ClassVar = PlannedItem
    FIELDS: ClassVar = {
        "name": "str", "kind": "str", "amount": "dec", "currency": "str", "frequency": "str",
        "start_date": "date", "end_date": "date", "account_id": "str", "category_id": "str",
        "is_essential": "bool", "is_active": "bool",
    }
    pk: Optional[str] = None
    user_id: str = ""
    name: str = ""
    kind: str = "expense"
    amount: Decimal = Decimal("0")
    currency: str = "USD"
    frequency: str = "monthly"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    account_id: str = ""
    category_id: str = ""
    is_essential: bool = False
    is_active: bool = True
    created_at: Optional[datetime] = None


RISK_SETTING_FIELDS = {
    "dti_warn": "decn", "dti_high": "decn", "balloon_warn": "decn", "balloon_high": "decn",
    "debt_assets_warn": "decn", "debt_assets_high": "decn", "emergency_warn_months": "decn",
    "emergency_high_months": "decn", "cash_flow_warn_pct": "decn", "horizon_months": "intn",
    "included_account_ids": "json", "alerts_enabled": "bool", "email_enabled": "bool",
}


@dataclass
class RiskSettingsFS(_OrmAdapter):
    _model: ClassVar = RiskSettings
    FIELDS: ClassVar = RISK_SETTING_FIELDS
    pk: Optional[str] = None
    user_id: str = ""
    dti_warn: Optional[Decimal] = None
    dti_high: Optional[Decimal] = None
    balloon_warn: Optional[Decimal] = None
    balloon_high: Optional[Decimal] = None
    debt_assets_warn: Optional[Decimal] = None
    debt_assets_high: Optional[Decimal] = None
    emergency_warn_months: Optional[Decimal] = None
    emergency_high_months: Optional[Decimal] = None
    cash_flow_warn_pct: Optional[Decimal] = None
    horizon_months: Optional[int] = None
    included_account_ids: List[str] = field(default_factory=list)
    alerts_enabled: bool = True
    email_enabled: bool = True
    created_at: Optional[datetime] = None

    @classmethod
    def get_for_user(cls, user_id: str):
        rows = cls.list_by_user(user_id, limit=1)
        return rows[0] if rows else None


@dataclass
class RiskSnapshotFS(_OrmAdapter):
    _model: ClassVar = RiskSnapshot
    FIELDS: ClassVar = {"as_of": "date", "score": "intn", "level": "str", "factors": "json"}
    pk: Optional[str] = None
    user_id: str = ""
    as_of: Optional[date] = None
    score: Optional[int] = None
    level: str = ""
    factors: List[Dict[str, Any]] = field(default_factory=list)
    created_at: Optional[datetime] = None

    @classmethod
    def get_for_day(cls, user_id: str, as_of: date):
        rows = cls.list_by_user(user_id, limit=1, as_of=as_of)
        return rows[0] if rows else None

    @classmethod
    def list_since(cls, user_id: str, since: date) -> List:
        rows = [r for r in cls.list_by_user(user_id, limit=1000) if r.as_of and r.as_of >= since]
        rows.sort(key=lambda r: r.as_of)
        return rows
