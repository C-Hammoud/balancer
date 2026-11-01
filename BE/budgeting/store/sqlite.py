"""
Django ORM-backed adapters mirroring budgeting/firestore_models.py API.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, Dict, List, Optional, Type

from django.contrib.auth import get_user_model
from django.db import models
from budgeting.alert_state import alert_is_snoozed
from budgeting.models import (
    Budget,
    BudgetAlert,
    BudgetThreshold,
    Category,
    Commitment,
    CommitmentScheduleLine,
    FinancialStanding,
    Group,
    IncomeSource,
    MerchantCategoryLink,
    PersonalBudget,
    PersonalBudgetCategory,
    PersonalBudgetMember,
    PersonalBudgetNotification,
    PersonalBudgetInvite,
    Savings,
    Transaction,
    TypeCategoryMap,
    UploadTemplate,
    UserPreferences,
)

CONSUMPTION_TYPES = ("market", "transport", "food", "other")


def _as_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def _as_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _as_datetime(value) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    try:
        s = str(value)
        if "T" in s:
            return datetime.fromisoformat(s.replace("Z", "+00:00"))
        return datetime.fromisoformat(s[:10])
    except Exception:
        return None


def _str_pk(pk: Optional[int]) -> Optional[str]:
    return str(pk) if pk is not None else None


def _int_pk(pk: Optional[str]) -> Optional[int]:
    if pk is None or pk == "":
        return None
    return int(pk)


def _fk_str(fk_id: Optional[int]) -> str:
    return str(fk_id) if fk_id is not None else ""


def _optional_fk_str(fk_id: Optional[int]) -> Optional[str]:
    if fk_id is None:
        return None
    return str(fk_id)


def _user_id_str(user_id: Optional[int]) -> str:
    return str(user_id) if user_id is not None else ""


def _optional_user_id_str(user_id: Optional[int]) -> Optional[str]:
    if user_id is None:
        return None
    return str(user_id)


class SqliteAdapterMixin:
    """Shared CRUD helpers for Django model adapters."""

    _model: ClassVar[Type[models.Model]]

    @classmethod
    def from_model(cls, obj: models.Model):
        raise NotImplementedError

    @classmethod
    def get(cls, pk: str):
        try:
            obj = cls._model.objects.get(pk=_int_pk(pk))
            return cls.from_model(obj)
        except (cls._model.DoesNotExist, TypeError, ValueError):
            return None

    @classmethod
    def list_all(cls, limit: int = 500) -> List:
        return [cls.from_model(o) for o in cls._model.objects.all()[:limit]]

    @classmethod
    def query_by_field(cls, field_name: str, op: str, value, limit: int = 500) -> List:
        if op != "==":
            raise NotImplementedError(f"Unsupported op {op!r}")
        qs = cls._apply_field_filter(field_name, value)
        return [cls.from_model(o) for o in qs[:limit]]

    @classmethod
    def _apply_field_filter(cls, field_name: str, value):
        if field_name == "user_id":
            if value in (None, ""):
                return cls._model.objects.filter(user__isnull=True)
            return cls._model.objects.filter(user_id=int(value))
        if field_name == "commitment_id":
            return cls._model.objects.filter(commitment_id=int(value))
        if field_name == "external_id":
            return cls._model.objects.filter(external_id=value)
        if field_name == "fingerprint":
            return cls._model.objects.filter(fingerprint=value)
        return cls._model.objects.filter(**{field_name: value})

    def delete(self):
        pk = _int_pk(self.pk)
        if pk is None:
            return
        cls = type(self)
        cls._model.objects.filter(pk=pk).delete()


@dataclass
class GroupFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = Group

    pk: Optional[str] = None
    name: str = ""
    order: int = 0
    user_id: str = ""  # "" = shared default

    def to_dict(self) -> Dict[str, Any]:
        return {"name": self.name, "order": self.order, "user_id": self.user_id or ""}

    @classmethod
    def from_model(cls, obj: Group):
        return cls(
            pk=_str_pk(obj.pk),
            name=obj.name,
            order=int(obj.order or 0),
            user_id=_optional_user_id_str(obj.user_id) or "",
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.name = data.get("name", "") or ""
        o.order = int(data.get("order", 0) or 0)
        o.user_id = data.get("user_id", "") or ""
        return o

    def save(self):
        if self.pk:
            obj = Group.objects.get(pk=_int_pk(self.pk))
        else:
            obj = Group()
        obj.name = self.name
        obj.order = int(self.order or 0)
        obj.user_id = int(self.user_id) if self.user_id else None
        obj.save()
        self.pk = _str_pk(obj.pk)
        return self


@dataclass
class CategoryFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = Category

    pk: Optional[str] = None
    name: str = ""
    group_id: str = ""
    include_in_reports: bool = True
    order: int = 0
    user_id: str = ""  # "" = shared default

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "group_id": self.group_id,
            "include_in_reports": self.include_in_reports,
            "order": self.order,
            "user_id": self.user_id or "",
        }

    @classmethod
    def from_model(cls, obj: Category):
        return cls(
            pk=_str_pk(obj.pk),
            name=obj.name,
            group_id=_fk_str(obj.group_id),
            include_in_reports=bool(obj.include_in_reports),
            order=int(obj.order or 0),
            user_id=_optional_user_id_str(obj.user_id) or "",
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.name = data.get("name", "") or ""
        o.group_id = data.get("group_id", "") or ""
        o.include_in_reports = bool(data.get("include_in_reports", True))
        o.order = int(data.get("order", 0) or 0)
        o.user_id = data.get("user_id", "") or ""
        return o

    def save(self):
        if self.pk:
            obj = Category.objects.get(pk=_int_pk(self.pk))
        else:
            obj = Category()
        obj.name = self.name
        obj.group_id = _int_pk(self.group_id)
        obj.include_in_reports = bool(self.include_in_reports)
        obj.order = int(self.order or 0)
        obj.user_id = int(self.user_id) if self.user_id else None
        obj.save()
        self.pk = _str_pk(obj.pk)
        return self


@dataclass
class TransactionFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = Transaction

    pk: Optional[str] = None
    user_id: str = ""
    date: Optional[date] = None
    month: str = ""
    description: str = ""
    category_id: Optional[str] = None
    classification: Optional[str] = None
    amount: Decimal = Decimal("0")
    direction: str = "expense"
    currency: str = "USD"
    note: str = ""
    time: str = ""
    source_account: str = ""
    income_source_id: str = ""
    commitment_id: str = ""
    schedule_line_id: str = ""
    external_id: str = ""
    include_in_utilization: bool = False
    budget_id: str = ""
    budget_category_id: str = ""
    to_account_id: str = ""
    status: str = "settled"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "date": self.date.isoformat() if self.date else None,
            "month": self.month,
            "description": (self.description or "")[:500],
            "category_id": self.category_id,
            "classification": self.classification,
            "amount": str(self.amount),
            "direction": self.direction,
            "currency": self.currency or "USD",
            "note": self.note or "",
            "time": (self.time or "")[:8],
            "source_account": self.source_account or "",
            "income_source_id": self.income_source_id or "",
            "commitment_id": self.commitment_id or "",
            "schedule_line_id": self.schedule_line_id or "",
            "external_id": self.external_id or "",
            "include_in_utilization": bool(self.include_in_utilization),
            "budget_id": self.budget_id or "",
            "budget_category_id": self.budget_category_id or "",
            "to_account_id": self.to_account_id or "",
            "status": self.status or "settled",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_model(cls, obj: Transaction):
        return cls(
            pk=_str_pk(obj.pk),
            user_id=_user_id_str(obj.user_id),
            date=obj.date,
            month=obj.month or "",
            description=obj.description or "",
            category_id=_optional_fk_str(obj.category_id),
            classification=obj.classification,
            amount=obj.amount,
            direction=obj.direction,
            currency=obj.currency or "USD",
            note=obj.note or "",
            time=(obj.time or "")[:8],
            source_account=obj.source_account or "",
            income_source_id=obj.income_source_id or "",
            commitment_id=obj.commitment_id or "",
            schedule_line_id=obj.schedule_line_id or "",
            external_id=obj.external_id or "",
            include_in_utilization=bool(obj.include_in_utilization),
            budget_id=obj.budget_id or "",
            budget_category_id=obj.budget_category_id or "",
            to_account_id=obj.to_account_id or "",
            status=obj.status or "settled",
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id", "") or ""
        o.date = _as_date(data.get("date"))
        o.month = data.get("month", "") or ""
        o.description = data.get("description", "") or ""
        o.category_id = data.get("category_id")
        o.classification = data.get("classification")
        o.amount = _as_decimal(data.get("amount", "0"))
        o.direction = data.get("direction", "expense")
        o.currency = data.get("currency", "USD") or "USD"
        o.note = data.get("note", "") or ""
        o.time = (data.get("time") or "")[:8]
        o.source_account = data.get("source_account", "") or ""
        o.income_source_id = data.get("income_source_id", "") or ""
        o.commitment_id = data.get("commitment_id", "") or ""
        o.schedule_line_id = data.get("schedule_line_id", "") or ""
        o.external_id = data.get("external_id", "") or ""
        o.include_in_utilization = bool(data.get("include_in_utilization", False))
        o.budget_id = data.get("budget_id", "") or ""
        o.budget_category_id = data.get("budget_category_id", "") or ""
        o.to_account_id = data.get("to_account_id", "") or ""
        o.status = data.get("status", "settled") or "settled"
        o.created_at = _as_datetime(data.get("created_at"))
        o.updated_at = _as_datetime(data.get("updated_at"))
        return o

    def save(self):
        if self.pk:
            obj = Transaction.objects.get(pk=_int_pk(self.pk))
        else:
            obj = Transaction()
        obj.user_id = int(self.user_id)
        obj.date = self.date
        obj.month = self.month
        obj.description = (self.description or "")[:500]
        obj.category_id = _int_pk(self.category_id) if self.category_id else None
        obj.classification = self.classification
        obj.amount = self.amount
        obj.direction = self.direction
        obj.currency = self.currency or "USD"
        obj.note = self.note or ""
        obj.time = (self.time or "")[:8]
        obj.source_account = self.source_account or ""
        obj.income_source_id = self.income_source_id or ""
        obj.commitment_id = self.commitment_id or ""
        obj.schedule_line_id = self.schedule_line_id or ""
        obj.external_id = self.external_id or ""
        obj.include_in_utilization = bool(self.include_in_utilization)
        obj.budget_id = self.budget_id or ""
        obj.budget_category_id = self.budget_category_id or ""
        obj.to_account_id = self.to_account_id or ""
        obj.status = self.status or "settled"
        obj.save()
        self.pk = _str_pk(obj.pk)
        self.created_at = obj.created_at
        self.updated_at = obj.updated_at
        return self

    @classmethod
    def list_all_for_user(cls, user_id: str) -> List:
        """Every transaction of the user (no limit): used for account balances."""
        return [cls.from_model(o) for o in Transaction.objects.filter(user_id=int(user_id)).order_by("date", "id")]

    @classmethod
    def list_by_user(cls, user_id: str, month: Optional[str] = None, limit: int = 500) -> List:
        qs = Transaction.objects.filter(user_id=int(user_id))
        if month:
            qs = qs.filter(month=month)
        out = [cls.from_model(o) for o in qs[:1000]]
        out.sort(key=lambda t: (t.date or date(1970, 1, 1)), reverse=True)
        return out[:limit]

    @classmethod
    def list_by_budget(cls, budget_id: str, limit: int = 2000) -> List:
        if not budget_id:
            return []
        qs = Transaction.objects.filter(budget_id=str(budget_id)).order_by("-date", "-id")[:limit]
        return [cls.from_model(o) for o in qs]

    @classmethod
    def exists_by_external_id(cls, user_id: str, external_id: str) -> bool:
        return Transaction.objects.filter(
            user_id=int(user_id),
            external_id=external_id,
        ).exists()

    @classmethod
    def get_by_external_id(cls, user_id: str, external_id: str):
        obj = Transaction.objects.filter(
            user_id=int(user_id),
            external_id=external_id,
        ).first()
        return cls.from_model(obj) if obj else None


@dataclass
class MerchantCategoryLinkFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = MerchantCategoryLink

    pk: Optional[str] = None
    keyword: str = ""
    category_id: str = ""
    user_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "keyword": self.keyword,
            "category_id": self.category_id,
            "user_id": self.user_id,
        }

    @classmethod
    def from_model(cls, obj: MerchantCategoryLink):
        return cls(
            pk=_str_pk(obj.pk),
            keyword=obj.keyword,
            category_id=_fk_str(obj.category_id),
            user_id=_optional_user_id_str(obj.user_id),
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.keyword = data.get("keyword", "") or ""
        o.category_id = data.get("category_id", "") or ""
        o.user_id = data.get("user_id")
        return o

    def save(self):
        if self.pk:
            obj = MerchantCategoryLink.objects.get(pk=_int_pk(self.pk))
        else:
            obj = MerchantCategoryLink()
        obj.keyword = self.keyword
        obj.category_id = _int_pk(self.category_id)
        obj.user_id = _int_pk(self.user_id) if self.user_id else None
        obj.save()
        self.pk = _str_pk(obj.pk)
        return self

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 500) -> List:
        return cls.query_by_field("user_id", "==", str(user_id), limit=limit)


@dataclass
class BudgetFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = Budget

    pk: Optional[str] = None
    user_id: str = ""
    category_id: str = ""
    group_id: str = ""
    year: int = 0
    month: int = 0
    forecast: Decimal = Decimal("0")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "category_id": self.category_id or "",
            "group_id": self.group_id or "",
            "year": self.year,
            "month": self.month,
            "forecast": str(self.forecast),
        }

    @classmethod
    def from_model(cls, obj: Budget):
        return cls(
            pk=_str_pk(obj.pk),
            user_id=_user_id_str(obj.user_id),
            category_id=_fk_str(obj.category_id),
            group_id=_fk_str(obj.group_id),
            year=int(obj.year),
            month=int(obj.month),
            forecast=obj.forecast,
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id", "") or ""
        o.category_id = data.get("category_id", "") or ""
        o.group_id = data.get("group_id", "") or ""
        o.year = int(data.get("year", 0) or 0)
        o.month = int(data.get("month", 0) or 0)
        o.forecast = _as_decimal(data.get("forecast", "0"))
        return o

    def save(self):
        if self.pk:
            obj = Budget.objects.get(pk=_int_pk(self.pk))
        else:
            obj = Budget()
        obj.user_id = int(self.user_id)
        if (self.category_id or "").strip():
            obj.category_id = _int_pk(self.category_id)
            obj.group_id = None
        else:
            obj.category_id = None
            obj.group_id = _int_pk(self.group_id) if (self.group_id or "").strip() else None
        obj.year = int(self.year)
        obj.month = int(self.month)
        obj.forecast = self.forecast
        obj.save()
        self.pk = _str_pk(obj.pk)
        return self

    @classmethod
    def list_by_user(
        cls,
        user_id: str,
        year: Optional[int] = None,
        month: Optional[int] = None,
        limit: int = 1000,
    ) -> List:
        qs = Budget.objects.filter(user_id=int(user_id))
        if year is not None:
            qs = qs.filter(year=year)
        if month is not None:
            qs = qs.filter(month=month)
        out = [cls.from_model(o) for o in qs[:limit]]
        out.sort(key=lambda x: (x.year, x.month, x.group_id, x.category_id))
        return out

    @classmethod
    def get_by_user_group_month(cls, user_id: str, group_id: str, year: int, month: int):
        obj = Budget.objects.filter(
            user_id=int(user_id),
            group_id=int(group_id),
            year=year,
            month=month,
            category__isnull=True,
        ).first()
        return cls.from_model(obj) if obj else None

    @classmethod
    def get_by_user_category_month(cls, user_id: str, category_id: str, year: int, month: int):
        obj = Budget.objects.filter(
            user_id=int(user_id),
            category_id=int(category_id),
            year=year,
            month=month,
        ).first()
        return cls.from_model(obj) if obj else None


@dataclass
class SavingsFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = Savings

    pk: Optional[str] = None
    user_id: str = ""
    year: int = 0
    month: int = 0
    actual: Optional[Decimal] = None
    target: Decimal = Decimal("0")
    goal_status: str = "pending"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "year": self.year,
            "month": self.month,
            "actual": str(self.actual) if self.actual is not None else None,
            "target": str(self.target),
            "goal_status": self.goal_status,
        }

    @classmethod
    def from_model(cls, obj: Savings):
        return cls(
            pk=_str_pk(obj.pk),
            user_id=_user_id_str(obj.user_id),
            year=int(obj.year),
            month=int(obj.month),
            actual=obj.actual,
            target=obj.target,
            goal_status=obj.goal_status or "pending",
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id", "") or ""
        o.year = int(data.get("year", 0) or 0)
        o.month = int(data.get("month", 0) or 0)
        a = data.get("actual")
        o.actual = _as_decimal(a) if a is not None else None
        o.target = _as_decimal(data.get("target", "0"))
        o.goal_status = data.get("goal_status", "pending") or "pending"
        return o

    def save(self):
        if self.pk:
            obj = Savings.objects.get(pk=_int_pk(self.pk))
        else:
            obj = Savings.objects.filter(
                user_id=int(self.user_id),
                year=int(self.year),
                month=int(self.month),
            ).first()
            if obj is None:
                obj = Savings()
        obj.user_id = int(self.user_id)
        obj.year = int(self.year)
        obj.month = int(self.month)
        obj.actual = self.actual
        obj.target = self.target
        obj.goal_status = self.goal_status or "pending"
        obj.save()
        self.pk = _str_pk(obj.pk)
        return self

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 100) -> List:
        out = [cls.from_model(o) for o in Savings.objects.filter(user_id=int(user_id))[:limit]]
        out.sort(key=lambda x: (x.year, x.month), reverse=True)
        return out[:limit]

    @classmethod
    def get_by_user_month(cls, user_id: str, year: int, month: int):
        obj = Savings.objects.filter(
            user_id=int(user_id),
            year=year,
            month=month,
        ).first()
        return cls.from_model(obj) if obj else None


@dataclass
class CommitmentFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = Commitment

    pk: Optional[str] = None
    user_id: str = ""
    name: str = ""
    amount: Decimal = Decimal("0")
    start_date: Optional[date] = None
    term_months: int = 0
    frequency: str = "monthly"
    payment_amount: Decimal = Decimal("0")
    balloon: Decimal = Decimal("0")
    currency: str = "USD"
    reminder_enabled: bool = True
    reminder_days_before: int = 3
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "amount": str(self.amount),
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "term_months": self.term_months,
            "frequency": self.frequency,
            "payment_amount": str(self.payment_amount),
            "balloon": str(self.balloon),
            "currency": self.currency or "USD",
            "reminder_enabled": self.reminder_enabled,
            "reminder_days_before": int(self.reminder_days_before),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_model(cls, obj: Commitment):
        return cls(
            pk=_str_pk(obj.pk),
            user_id=_user_id_str(obj.user_id),
            name=obj.name,
            amount=obj.amount,
            start_date=obj.start_date,
            term_months=int(obj.term_months or 0),
            frequency=obj.frequency or "monthly",
            payment_amount=obj.payment_amount,
            balloon=obj.balloon,
            currency=obj.currency or "USD",
            reminder_enabled=bool(obj.reminder_enabled),
            reminder_days_before=int(obj.reminder_days_before or 3),
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id", "") or ""
        o.name = data.get("name", "") or ""
        o.amount = _as_decimal(data.get("amount", "0"))
        o.start_date = _as_date(data.get("start_date"))
        o.term_months = int(data.get("term_months", 0) or 0)
        o.frequency = data.get("frequency", "monthly") or "monthly"
        o.payment_amount = _as_decimal(data.get("payment_amount", "0"))
        o.balloon = _as_decimal(data.get("balloon", "0"))
        o.currency = data.get("currency", "USD") or "USD"
        o.reminder_enabled = bool(data.get("reminder_enabled", True))
        o.reminder_days_before = int(data.get("reminder_days_before", 3) or 3)
        o.created_at = _as_datetime(data.get("created_at"))
        o.updated_at = _as_datetime(data.get("updated_at"))
        return o

    def save(self):
        if self.pk:
            obj = Commitment.objects.get(pk=_int_pk(self.pk))
        else:
            obj = Commitment()
        obj.user_id = int(self.user_id)
        obj.name = self.name
        obj.amount = self.amount
        obj.start_date = self.start_date
        obj.term_months = int(self.term_months or 0)
        obj.frequency = self.frequency or "monthly"
        obj.payment_amount = self.payment_amount
        obj.balloon = self.balloon
        obj.currency = self.currency or "USD"
        obj.reminder_enabled = bool(self.reminder_enabled)
        obj.reminder_days_before = int(self.reminder_days_before or 3)
        obj.save()
        self.pk = _str_pk(obj.pk)
        self.created_at = obj.created_at
        self.updated_at = obj.updated_at
        return self

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 100) -> List:
        return cls.query_by_field("user_id", "==", str(user_id), limit=limit)


@dataclass
class CommitmentScheduleLineFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = CommitmentScheduleLine

    pk: Optional[str] = None
    commitment_id: str = ""
    due_date: Optional[date] = None
    amount: Decimal = Decimal("0")
    status: str = "outstanding"
    sequence: int = 0
    paid_date: Optional[date] = None
    reminder_sent: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "commitment_id": self.commitment_id,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "amount": str(self.amount),
            "status": self.status,
            "sequence": self.sequence,
            "paid_date": self.paid_date.isoformat() if self.paid_date else None,
            "reminder_sent": bool(self.reminder_sent),
        }

    @classmethod
    def from_model(cls, obj: CommitmentScheduleLine):
        return cls(
            pk=_str_pk(obj.pk),
            commitment_id=_fk_str(obj.commitment_id),
            due_date=obj.due_date,
            amount=obj.amount,
            status=obj.status or "outstanding",
            sequence=int(obj.sequence or 0),
            paid_date=obj.paid_date,
            reminder_sent=bool(obj.reminder_sent),
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.commitment_id = data.get("commitment_id", "") or ""
        o.due_date = _as_date(data.get("due_date"))
        o.amount = _as_decimal(data.get("amount", "0"))
        o.status = data.get("status", "outstanding") or "outstanding"
        o.sequence = int(data.get("sequence", 0) or 0)
        o.paid_date = _as_date(data.get("paid_date"))
        o.reminder_sent = bool(data.get("reminder_sent", False))
        return o

    def save(self):
        if self.pk:
            obj = CommitmentScheduleLine.objects.get(pk=_int_pk(self.pk))
        else:
            obj = CommitmentScheduleLine()
        obj.commitment_id = _int_pk(self.commitment_id)
        obj.due_date = self.due_date
        obj.amount = self.amount
        obj.status = self.status or "outstanding"
        obj.sequence = int(self.sequence or 0)
        obj.paid_date = self.paid_date
        obj.reminder_sent = bool(self.reminder_sent)
        obj.save()
        self.pk = _str_pk(obj.pk)
        return self

    @classmethod
    def list_by_commitment(cls, commitment_id: str, limit: int = 500, *, cleanup_duplicates: bool = True) -> List:
        out = [
            cls.from_model(o)
            for o in CommitmentScheduleLine.objects.filter(commitment_id=int(commitment_id))[:limit]
        ]
        out.sort(key=lambda x: (x.due_date or date(1970, 1, 1), x.sequence))
        if cleanup_duplicates and len(out) > 1:
            out = cls._dedupe_and_cleanup(out)
        return out[:limit]

    @classmethod
    def _pick_preferred_line(cls, a, b):
        if a.status == "paid" and b.status != "paid":
            return a, b
        if b.status == "paid" and a.status != "paid":
            return b, a
        if a.paid_date and not b.paid_date:
            return a, b
        if b.paid_date and not a.paid_date:
            return b, a
        if (a.pk or "") <= (b.pk or ""):
            return a, b
        return b, a

    @classmethod
    def _dedupe_and_cleanup(cls, lines: List) -> List:
        lines.sort(key=lambda x: (x.due_date or date(1970, 1, 1), x.sequence))
        return lines

    @classmethod
    def delete_by_commitment(cls, commitment_id: str) -> int:
        deleted, _ = CommitmentScheduleLine.objects.filter(commitment_id=int(commitment_id)).delete()
        return deleted

    @classmethod
    def sum_outstanding_by_commitment(cls, commitment_id: str) -> Decimal:
        lines = cls.list_by_commitment(commitment_id)
        return sum((line.amount for line in lines if line.status == "outstanding"), Decimal("0"))

    @classmethod
    def sum_amount_due_in_month(cls, user_id: str, year: int, month: int) -> Decimal:
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        commitments = CommitmentFS.list_by_user(user_id)
        total = Decimal("0")
        for commitment in commitments:
            for line in cls.list_by_commitment(commitment.pk):
                if line.status != "outstanding":
                    continue
                if line.due_date and start <= line.due_date < end:
                    total += line.amount
        return total


@dataclass
class FinancialStandingFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = FinancialStanding

    pk: Optional[str] = None
    user_id: str = ""
    snapshot_date: Optional[date] = None
    total_assets: Decimal = Decimal("0")
    current_assets: Decimal = Decimal("0")
    fixed_assets: Decimal = Decimal("0")
    total_liabilities: Decimal = Decimal("0")
    short_term_liabilities: Decimal = Decimal("0")
    long_term_liabilities: Decimal = Decimal("0")
    notes: str = ""
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "snapshot_date": self.snapshot_date.isoformat() if self.snapshot_date else None,
            "total_assets": str(self.total_assets),
            "current_assets": str(self.current_assets),
            "fixed_assets": str(self.fixed_assets),
            "total_liabilities": str(self.total_liabilities),
            "short_term_liabilities": str(self.short_term_liabilities),
            "long_term_liabilities": str(self.long_term_liabilities),
            "notes": self.notes or "",
            "created_at": self.created_at,
        }

    @classmethod
    def from_model(cls, obj: FinancialStanding):
        return cls(
            pk=_str_pk(obj.pk),
            user_id=_user_id_str(obj.user_id),
            snapshot_date=obj.snapshot_date,
            total_assets=obj.total_assets,
            current_assets=obj.current_assets,
            fixed_assets=obj.fixed_assets,
            total_liabilities=obj.total_liabilities,
            short_term_liabilities=obj.short_term_liabilities,
            long_term_liabilities=obj.long_term_liabilities,
            notes=obj.notes or "",
            created_at=obj.created_at,
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id", "") or ""
        o.snapshot_date = _as_date(data.get("snapshot_date"))
        o.total_assets = _as_decimal(data.get("total_assets", "0"))
        o.current_assets = _as_decimal(data.get("current_assets", "0"))
        o.fixed_assets = _as_decimal(data.get("fixed_assets", "0"))
        o.total_liabilities = _as_decimal(data.get("total_liabilities", "0"))
        o.short_term_liabilities = _as_decimal(data.get("short_term_liabilities", "0"))
        o.long_term_liabilities = _as_decimal(data.get("long_term_liabilities", "0"))
        o.notes = data.get("notes", "") or ""
        o.created_at = _as_datetime(data.get("created_at"))
        return o

    def save(self):
        if self.pk:
            obj = FinancialStanding.objects.get(pk=_int_pk(self.pk))
        else:
            obj = FinancialStanding()
        obj.user_id = int(self.user_id)
        obj.snapshot_date = self.snapshot_date
        obj.total_assets = self.total_assets
        obj.current_assets = self.current_assets
        obj.fixed_assets = self.fixed_assets
        obj.total_liabilities = self.total_liabilities
        obj.short_term_liabilities = self.short_term_liabilities
        obj.long_term_liabilities = self.long_term_liabilities
        obj.notes = self.notes or ""
        obj.save()
        self.pk = _str_pk(obj.pk)
        self.created_at = obj.created_at
        return self

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 100) -> List:
        out = [
            cls.from_model(o)
            for o in FinancialStanding.objects.filter(user_id=int(user_id))[:limit]
        ]
        out.sort(key=lambda x: x.snapshot_date or date(1970, 1, 1), reverse=True)
        return out[:limit]


@dataclass
class UploadTemplateFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = UploadTemplate

    pk: Optional[str] = None
    user_id: Optional[str] = None
    name: str = ""
    column_mapping: Dict = field(default_factory=dict)
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "column_mapping": self.column_mapping or {},
            "created_at": self.created_at,
        }

    @classmethod
    def from_model(cls, obj: UploadTemplate):
        return cls(
            pk=_str_pk(obj.pk),
            user_id=_optional_user_id_str(obj.user_id),
            name=obj.name,
            column_mapping=obj.column_mapping or {},
            created_at=obj.created_at,
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id")
        o.name = data.get("name", "") or ""
        o.column_mapping = data.get("column_mapping") or {}
        o.created_at = _as_datetime(data.get("created_at"))
        return o

    def save(self):
        if self.pk:
            obj = UploadTemplate.objects.get(pk=_int_pk(self.pk))
        else:
            obj = UploadTemplate()
        obj.user_id = _int_pk(self.user_id) if self.user_id else None
        obj.name = self.name
        obj.column_mapping = self.column_mapping or {}
        obj.save()
        self.pk = _str_pk(obj.pk)
        self.created_at = obj.created_at
        return self


@dataclass
class TypeCategoryMapFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = TypeCategoryMap

    pk: Optional[str] = None
    user_id: Optional[str] = None
    consumption_type: str = "other"
    category_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "consumption_type": self.consumption_type,
            "category_id": self.category_id,
        }

    @classmethod
    def from_model(cls, obj: TypeCategoryMap):
        return cls(
            pk=_str_pk(obj.pk),
            user_id=_optional_user_id_str(obj.user_id),
            consumption_type=(obj.consumption_type or "other").lower(),
            category_id=_fk_str(obj.category_id),
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id")
        o.consumption_type = (data.get("consumption_type") or "other").lower()
        o.category_id = data.get("category_id", "") or ""
        return o

    def save(self):
        if self.pk:
            obj = TypeCategoryMap.objects.get(pk=_int_pk(self.pk))
        else:
            obj = TypeCategoryMap()
        obj.user_id = _int_pk(self.user_id) if self.user_id else None
        obj.consumption_type = (self.consumption_type or "other").lower()
        obj.category_id = _int_pk(self.category_id)
        obj.save()
        self.pk = _str_pk(obj.pk)
        return self

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 50) -> List:
        return cls.query_by_field("user_id", "==", str(user_id), limit=limit)

    @classmethod
    def list_global(cls, limit: int = 50) -> List:
        return [cls.from_model(o) for o in TypeCategoryMap.objects.filter(user__isnull=True)[:limit]]

    @classmethod
    def get_map_for_user(cls, user_id: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for mapping in cls.list_global():
            if mapping.consumption_type:
                result[mapping.consumption_type] = mapping.category_id
        for mapping in cls.list_by_user(user_id):
            if mapping.consumption_type:
                result[mapping.consumption_type] = mapping.category_id
        return result

    @classmethod
    def get_for_user_type(cls, user_id: str, consumption_type: str):
        ctype = (consumption_type or "other").lower()
        for mapping in cls.list_by_user(user_id):
            if mapping.consumption_type == ctype:
                return mapping
        for mapping in cls.list_global():
            if mapping.consumption_type == ctype:
                return mapping
        return None


@dataclass
class BudgetThresholdFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = BudgetThreshold

    pk: Optional[str] = None
    user_id: str = ""
    category_id: Optional[str] = None
    warn_pct: Decimal = Decimal("80")
    critical_pct: Decimal = Decimal("100")
    email_enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "category_id": self.category_id or "",
            "warn_pct": str(self.warn_pct),
            "critical_pct": str(self.critical_pct),
            "email_enabled": self.email_enabled,
        }

    @classmethod
    def from_model(cls, obj: BudgetThreshold):
        return cls(
            pk=_str_pk(obj.pk),
            user_id=_user_id_str(obj.user_id),
            category_id=_optional_fk_str(obj.category_id),
            warn_pct=obj.warn_pct,
            critical_pct=obj.critical_pct,
            email_enabled=bool(obj.email_enabled),
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id", "") or ""
        cid = data.get("category_id") or ""
        o.category_id = cid if cid else None
        o.warn_pct = _as_decimal(data.get("warn_pct", "80"))
        o.critical_pct = _as_decimal(data.get("critical_pct", "100"))
        o.email_enabled = bool(data.get("email_enabled", True))
        return o

    def save(self):
        if self.pk:
            obj = BudgetThreshold.objects.get(pk=_int_pk(self.pk))
        else:
            obj = BudgetThreshold()
        obj.user_id = int(self.user_id)
        obj.category_id = _int_pk(self.category_id) if self.category_id else None
        obj.warn_pct = self.warn_pct
        obj.critical_pct = self.critical_pct
        obj.email_enabled = bool(self.email_enabled)
        obj.save()
        self.pk = _str_pk(obj.pk)
        return self

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 200) -> List:
        return cls.query_by_field("user_id", "==", str(user_id), limit=limit)

    @classmethod
    def get_global_for_user(cls, user_id: str):
        for threshold in cls.list_by_user(user_id):
            if not threshold.category_id:
                return threshold
        return None

    @classmethod
    def get_for_category(cls, user_id: str, category_id: Optional[str]):
        thresholds = cls.list_by_user(user_id)
        if category_id:
            for threshold in thresholds:
                if threshold.category_id == category_id:
                    return threshold
        for threshold in thresholds:
            if not threshold.category_id:
                return threshold
        return None


@dataclass
class IncomeSourceFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = IncomeSource

    pk: Optional[str] = None
    user_id: str = ""
    name: str = ""
    account_type: str = "bank"
    order: int = 0
    is_active: bool = True
    is_default_for_expenses: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "account_type": self.account_type or "bank",
            "order": int(self.order),
            "is_active": bool(self.is_active),
            "is_default_for_expenses": bool(self.is_default_for_expenses),
        }

    @classmethod
    def from_model(cls, obj: IncomeSource):
        return cls(
            pk=_str_pk(obj.pk),
            user_id=_user_id_str(obj.user_id),
            name=obj.name,
            account_type=getattr(obj, "account_type", "bank") or "bank",
            order=int(obj.order or 0),
            is_active=bool(obj.is_active),
            is_default_for_expenses=bool(getattr(obj, "is_default_for_expenses", False)),
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id", "") or ""
        o.name = data.get("name", "") or ""
        o.account_type = data.get("account_type", "bank") or "bank"
        o.order = int(data.get("order", 0) or 0)
        o.is_active = bool(data.get("is_active", True))
        o.is_default_for_expenses = bool(data.get("is_default_for_expenses", False))
        return o

    def save(self):
        if self.pk:
            obj = IncomeSource.objects.get(pk=_int_pk(self.pk))
        else:
            obj = IncomeSource()
        obj.user_id = int(self.user_id)
        obj.name = self.name
        obj.account_type = self.account_type or "bank"
        obj.order = int(self.order or 0)
        obj.is_active = bool(self.is_active)
        obj.is_default_for_expenses = bool(self.is_default_for_expenses)
        obj.save()
        self.pk = _str_pk(obj.pk)
        return self

    @classmethod
    def list_by_user(cls, user_id: str, active_only: bool = False, limit: int = 200) -> List:
        rows = cls.query_by_field("user_id", "==", str(user_id), limit=limit)
        if active_only:
            rows = [row for row in rows if row.is_active]
        rows.sort(key=lambda x: (x.order, x.name.lower()))
        return rows


@dataclass
class BudgetAlertFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = BudgetAlert

    pk: Optional[str] = None
    user_id: str = ""
    year: int = 0
    month: int = 0
    category_id: str = ""
    severity: str = "WARN"
    title: str = ""
    description: str = ""
    alert_type: str = "utilization"
    utilization_pct: Optional[Decimal] = None
    actual: Decimal = Decimal("0")
    forecast: Decimal = Decimal("0")
    commitment_id: str = ""
    schedule_line_id: str = ""
    due_date: str = ""
    commitment_name: str = ""
    is_resolved: bool = False
    resolution: str = ""
    resolved_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None
    email_sent: bool = False
    fingerprint: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "year": self.year,
            "month": self.month,
            "category_id": self.category_id or "",
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "alert_type": self.alert_type or "utilization",
            "utilization_pct": str(self.utilization_pct) if self.utilization_pct is not None else None,
            "actual": str(self.actual),
            "forecast": str(self.forecast),
            "commitment_id": self.commitment_id or "",
            "schedule_line_id": self.schedule_line_id or "",
            "due_date": self.due_date or "",
            "commitment_name": self.commitment_name or "",
            "is_resolved": self.is_resolved,
            "resolution": self.resolution or "",
            "resolved_at": self.resolved_at,
            "snoozed_until": self.snoozed_until,
            "email_sent": self.email_sent,
            "fingerprint": self.fingerprint,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_model(cls, obj: BudgetAlert):
        return cls(
            pk=_str_pk(obj.pk),
            user_id=_user_id_str(obj.user_id),
            year=int(obj.year),
            month=int(obj.month),
            category_id=obj.category_id or "",
            severity=obj.severity or "WARN",
            title=obj.title or "",
            description=obj.description or "",
            alert_type=obj.alert_type or "utilization",
            utilization_pct=obj.utilization_pct,
            actual=obj.actual,
            forecast=obj.forecast,
            commitment_id=obj.commitment_id or "",
            schedule_line_id=obj.schedule_line_id or "",
            due_date=obj.due_date or "",
            commitment_name=obj.commitment_name or "",
            is_resolved=bool(obj.is_resolved),
            resolution=obj.resolution or "",
            resolved_at=obj.resolved_at,
            snoozed_until=obj.snoozed_until,
            email_sent=bool(obj.email_sent),
            fingerprint=obj.fingerprint or "",
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id", "") or ""
        o.year = int(data.get("year", 0) or 0)
        o.month = int(data.get("month", 0) or 0)
        o.category_id = data.get("category_id", "") or ""
        o.severity = data.get("severity", "WARN") or "WARN"
        o.title = data.get("title", "") or ""
        o.description = data.get("description", "") or ""
        o.alert_type = data.get("alert_type") or (
            "commitment_due"
            if (data.get("category_id") or "").startswith("commitment:")
            else "utilization"
        )
        up = data.get("utilization_pct")
        o.utilization_pct = _as_decimal(up) if up is not None else None
        o.actual = _as_decimal(data.get("actual", "0"))
        o.forecast = _as_decimal(data.get("forecast", "0"))
        o.commitment_id = data.get("commitment_id", "") or ""
        o.schedule_line_id = data.get("schedule_line_id", "") or ""
        o.due_date = data.get("due_date", "") or ""
        o.commitment_name = data.get("commitment_name", "") or ""
        o.is_resolved = bool(data.get("is_resolved", False))
        o.resolution = data.get("resolution", "") or ""
        o.resolved_at = _as_datetime(data.get("resolved_at"))
        o.snoozed_until = _as_datetime(data.get("snoozed_until"))
        o.email_sent = bool(data.get("email_sent", False))
        o.fingerprint = data.get("fingerprint", "") or ""
        o.created_at = _as_datetime(data.get("created_at"))
        o.updated_at = _as_datetime(data.get("updated_at"))
        return o

    def save(self):
        if self.pk:
            obj = BudgetAlert.objects.get(pk=_int_pk(self.pk))
        else:
            obj = BudgetAlert()
        obj.user_id = int(self.user_id)
        obj.year = int(self.year)
        obj.month = int(self.month)
        obj.category_id = self.category_id or ""
        obj.severity = self.severity
        obj.title = self.title
        obj.description = self.description
        obj.alert_type = self.alert_type or "utilization"
        obj.utilization_pct = self.utilization_pct
        obj.actual = self.actual
        obj.forecast = self.forecast
        obj.commitment_id = self.commitment_id or ""
        obj.schedule_line_id = self.schedule_line_id or ""
        obj.due_date = self.due_date or ""
        obj.commitment_name = self.commitment_name or ""
        obj.is_resolved = bool(self.is_resolved)
        obj.resolution = self.resolution or ""
        obj.resolved_at = self.resolved_at
        obj.snoozed_until = self.snoozed_until
        obj.email_sent = bool(self.email_sent)
        obj.fingerprint = self.fingerprint or ""
        obj.save()
        self.pk = _str_pk(obj.pk)
        self.created_at = obj.created_at
        self.updated_at = obj.updated_at
        return self

    @classmethod
    def list_by_user(cls, user_id: str, open_only: bool = False, limit: int = 200) -> List:
        out = cls.query_by_field("user_id", "==", str(user_id), limit=limit)
        if open_only:
            out = [alert for alert in out if not alert.is_resolved]
        out.sort(key=lambda alert: alert.created_at or datetime.min, reverse=True)
        return out

    @classmethod
    def count_open(cls, user_id: str) -> int:
        """Open alerts that are not currently snoozed (badge count)."""
        return sum(
            1 for alert in cls.list_by_user(user_id, open_only=True, limit=500)
            if not alert.is_snoozed()
        )

    @classmethod
    def get_by_fingerprint(cls, user_id: str, fingerprint: str):
        obj = BudgetAlert.objects.filter(
            user_id=int(user_id),
            fingerprint=fingerprint,
        ).first()
        return cls.from_model(obj) if obj else None

    @classmethod
    def list_for_month(cls, user_id: str, year: int, month: int, open_only: bool = False) -> List:
        out = [
            alert
            for alert in cls.list_by_user(user_id, open_only=False, limit=500)
            if alert.year == year and alert.month == month
        ]
        if open_only:
            out = [alert for alert in out if not alert.is_resolved]
        return out

    def is_snoozed(self, now: Optional[datetime] = None) -> bool:
        return alert_is_snoozed(self, now)

    @staticmethod
    def make_fingerprint(user_id: str, year: int, month: int, category_id: str, severity: str) -> str:
        return f"{user_id}|{year}|{month}|{category_id or '_'}|{severity}"


@dataclass
class UserPreferencesFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = UserPreferences

    pk: Optional[str] = None
    user_id: str = ""
    timezone: str = ""
    country: str = ""
    default_currency: str = "USD"
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "timezone": self.timezone or "",
            "country": self.country or "",
            "default_currency": self.default_currency or "USD",
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_model(cls, obj: UserPreferences):
        return cls(
            pk=_str_pk(obj.user_id),
            user_id=_user_id_str(obj.user_id),
            timezone=obj.timezone or "",
            country=obj.country or "",
            default_currency=obj.default_currency or "USD",
            updated_at=obj.updated_at,
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id", "") or doc_id
        o.timezone = data.get("timezone", "") or ""
        o.country = data.get("country", "") or ""
        o.default_currency = data.get("default_currency", "USD") or "USD"
        o.updated_at = _as_datetime(data.get("updated_at"))
        return o

    @classmethod
    def get(cls, pk: str):
        try:
            obj = UserPreferences.objects.get(user_id=_int_pk(pk))
            return cls.from_model(obj)
        except (UserPreferences.DoesNotExist, TypeError, ValueError):
            return None

    def save(self):
        User = get_user_model()
        user = User.objects.get(pk=int(self.user_id))
        obj, _ = UserPreferences.objects.update_or_create(
            user=user,
            defaults={
                "timezone": self.timezone or "",
                "country": self.country or "",
                "default_currency": self.default_currency or "USD",
            },
        )
        self.pk = _str_pk(user.pk)
        self.user_id = _str_pk(user.pk)
        self.updated_at = obj.updated_at
        return self

    def delete(self):
        if not self.pk and not self.user_id:
            return
        uid = _int_pk(self.pk or self.user_id)
        if uid is not None:
            UserPreferences.objects.filter(user_id=uid).delete()

    @classmethod
    def get_for_user(cls, user_id: str):
        return cls.get(str(user_id))

    @classmethod
    def get_or_create(cls, user_id: str, **defaults):
        uid = str(user_id)
        existing = cls.get_for_user(uid)
        if existing:
            return existing
        prefs = cls(pk=uid, user_id=uid, **defaults)
        prefs.save()
        return prefs


@dataclass
class PersonalBudgetFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = PersonalBudget

    pk: Optional[str] = None
    user_id: str = ""
    name: str = ""
    description: str = ""
    currency: str = "USD"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    total_amount: Decimal = Decimal("0")
    status: str = "draft"
    project_tag: str = ""
    notes: str = ""
    is_default: bool = False
    in_plan: bool = False
    funding_start: Optional[date] = None
    funding_months: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_model(cls, obj: PersonalBudget):
        return cls(
            pk=_str_pk(obj.pk),
            user_id=_user_id_str(obj.user_id),
            name=obj.name,
            description=obj.description or "",
            currency=obj.currency or "USD",
            start_date=obj.start_date,
            end_date=obj.end_date,
            total_amount=obj.total_amount,
            status=obj.status or "draft",
            project_tag=obj.project_tag or "",
            notes=obj.notes or "",
            is_default=bool(obj.is_default),
            in_plan=bool(obj.in_plan),
            funding_start=obj.funding_start,
            funding_months=int(obj.funding_months or 1),
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id", "") or ""
        o.name = data.get("name", "") or ""
        o.description = data.get("description", "") or ""
        o.currency = data.get("currency", "USD") or "USD"
        o.start_date = _as_date(data.get("start_date"))
        o.end_date = _as_date(data.get("end_date"))
        o.total_amount = _as_decimal(data.get("total_amount", "0"))
        o.status = data.get("status", "draft") or "draft"
        o.project_tag = data.get("project_tag", "") or ""
        o.notes = data.get("notes", "") or ""
        o.is_default = bool(data.get("is_default", False))
        o.in_plan = bool(data.get("in_plan", False))
        o.funding_start = _as_date(data.get("funding_start"))
        o.funding_months = int(data.get("funding_months") or 1)
        o.created_at = _as_datetime(data.get("created_at"))
        o.updated_at = _as_datetime(data.get("updated_at"))
        return o

    def save(self):
        if self.pk:
            obj = PersonalBudget.objects.get(pk=_int_pk(self.pk))
        else:
            obj = PersonalBudget()
        obj.user_id = int(self.user_id)
        obj.name = self.name
        obj.description = self.description or ""
        obj.currency = self.currency or "USD"
        obj.start_date = self.start_date
        obj.end_date = self.end_date
        obj.total_amount = self.total_amount
        obj.status = self.status or "draft"
        obj.project_tag = self.project_tag or ""
        obj.notes = self.notes or ""
        obj.is_default = bool(self.is_default)
        obj.in_plan = bool(self.in_plan)
        obj.funding_start = self.funding_start
        obj.funding_months = max(1, int(self.funding_months or 1))
        obj.save()
        self.pk = _str_pk(obj.pk)
        self.created_at = obj.created_at
        self.updated_at = obj.updated_at
        return self

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 500) -> List:
        qs = PersonalBudget.objects.filter(user_id=int(user_id)).order_by("-created_at")[:limit]
        rows = [cls.from_model(o) for o in qs]
        rows.sort(key=lambda b: (not b.is_default, b.name.lower()))
        return rows

    @classmethod
    def get_default_for_user(cls, user_id: str):
        for row in cls.list_by_user(user_id, limit=100):
            if row.is_default:
                return row
        return None


@dataclass
class PersonalBudgetCategoryFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = PersonalBudgetCategory

    pk: Optional[str] = None
    budget_id: str = ""
    name: str = ""
    allocated_amount: Decimal = Decimal("0")
    order: int = 0
    notes: str = ""
    group_id: str = ""
    category_id: str = ""
    parent_id: str = ""

    @classmethod
    def from_model(cls, obj: PersonalBudgetCategory):
        return cls(
            pk=_str_pk(obj.pk),
            budget_id=_fk_str(obj.budget_id),
            name=obj.name,
            allocated_amount=obj.allocated_amount,
            order=int(obj.order or 0),
            notes=obj.notes or "",
            group_id=getattr(obj, "group_id", "") or "",
            category_id=getattr(obj, "category_id", "") or "",
            parent_id=getattr(obj, "parent_id", "") or "",
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.budget_id = data.get("budget_id", "") or ""
        o.name = data.get("name", "") or ""
        o.allocated_amount = _as_decimal(data.get("allocated_amount", "0"))
        o.order = int(data.get("order", 0) or 0)
        o.notes = data.get("notes", "") or ""
        o.group_id = data.get("group_id", "") or ""
        o.category_id = data.get("category_id", "") or ""
        o.parent_id = data.get("parent_id", "") or ""
        return o

    def save(self):
        if self.pk:
            obj = PersonalBudgetCategory.objects.get(pk=_int_pk(self.pk))
        else:
            obj = PersonalBudgetCategory()
        obj.budget_id = _int_pk(self.budget_id)
        obj.name = self.name
        obj.allocated_amount = self.allocated_amount
        obj.order = int(self.order or 0)
        obj.notes = self.notes or ""
        obj.group_id = self.group_id or ""
        obj.category_id = self.category_id or ""
        obj.parent_id = self.parent_id or ""
        obj.save()
        self.pk = _str_pk(obj.pk)
        return self

    @classmethod
    def list_by_budget(cls, budget_id: str, limit: int = 200) -> List:
        qs = PersonalBudgetCategory.objects.filter(budget_id=_int_pk(budget_id)).order_by("order", "name")[:limit]
        return [cls.from_model(o) for o in qs]


@dataclass
class PersonalBudgetMemberFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = PersonalBudgetMember

    pk: Optional[str] = None
    budget_id: str = ""
    user_id: str = ""
    role: str = "viewer"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_model(cls, obj: PersonalBudgetMember):
        return cls(
            pk=_str_pk(obj.pk),
            budget_id=_fk_str(obj.budget_id),
            user_id=_user_id_str(obj.user_id),
            role=obj.role or "viewer",
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.budget_id = data.get("budget_id", "") or ""
        o.user_id = data.get("user_id", "") or ""
        o.role = data.get("role", "viewer") or "viewer"
        o.created_at = _as_datetime(data.get("created_at"))
        o.updated_at = _as_datetime(data.get("updated_at"))
        return o

    def save(self):
        if self.pk:
            obj = PersonalBudgetMember.objects.get(pk=_int_pk(self.pk))
        else:
            obj = PersonalBudgetMember()
        obj.budget_id = _int_pk(self.budget_id)
        obj.user_id = int(self.user_id)
        obj.role = self.role or "viewer"
        obj.save()
        self.pk = _str_pk(obj.pk)
        self.created_at = obj.created_at
        self.updated_at = obj.updated_at
        return self

    @classmethod
    def get_for_budget_user(cls, budget_id: str, user_id: str):
        obj = PersonalBudgetMember.objects.filter(
            budget_id=_int_pk(budget_id),
            user_id=int(user_id),
        ).first()
        return cls.from_model(obj) if obj else None

    @classmethod
    def list_by_budget(cls, budget_id: str, limit: int = 200) -> List:
        qs = PersonalBudgetMember.objects.filter(budget_id=_int_pk(budget_id)).order_by("created_at")[:limit]
        return [cls.from_model(o) for o in qs]

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 500) -> List:
        qs = PersonalBudgetMember.objects.filter(user_id=int(user_id)).order_by("-created_at")[:limit]
        return [cls.from_model(o) for o in qs]


@dataclass
class PersonalBudgetNotificationFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = PersonalBudgetNotification

    pk: Optional[str] = None
    recipient_id: str = ""
    budget_id: str = ""
    shared_by_id: str = ""
    role: str = "viewer"
    title: str = ""
    message: str = ""
    read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    @classmethod
    def from_model(cls, obj: PersonalBudgetNotification):
        return cls(
            pk=_str_pk(obj.pk),
            recipient_id=_user_id_str(obj.recipient_id),
            budget_id=_fk_str(obj.budget_id),
            shared_by_id=_user_id_str(obj.shared_by_id),
            role=obj.role or "viewer",
            title=obj.title,
            message=obj.message or "",
            read_at=obj.read_at,
            created_at=obj.created_at,
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.recipient_id = data.get("recipient_id", "") or ""
        o.budget_id = data.get("budget_id", "") or ""
        o.shared_by_id = data.get("shared_by_id", "") or ""
        o.role = data.get("role", "viewer") or "viewer"
        o.title = data.get("title", "") or ""
        o.message = data.get("message", "") or ""
        o.read_at = _as_datetime(data.get("read_at"))
        o.created_at = _as_datetime(data.get("created_at"))
        return o

    def save(self):
        if self.pk:
            obj = PersonalBudgetNotification.objects.get(pk=_int_pk(self.pk))
        else:
            obj = PersonalBudgetNotification()
        obj.recipient_id = int(self.recipient_id)
        obj.budget_id = _int_pk(self.budget_id)
        obj.shared_by_id = int(self.shared_by_id)
        obj.role = self.role or "viewer"
        obj.title = self.title
        obj.message = self.message or ""
        obj.read_at = self.read_at
        obj.save()
        self.pk = _str_pk(obj.pk)
        self.created_at = obj.created_at
        return self

    @classmethod
    def list_for_recipient(cls, user_id: str, limit: int = 100) -> List:
        qs = PersonalBudgetNotification.objects.filter(recipient_id=int(user_id)).order_by("-created_at")[:limit]
        return [cls.from_model(o) for o in qs]


@dataclass
class PersonalBudgetInviteFS(SqliteAdapterMixin):
    _model: ClassVar[Type[models.Model]] = PersonalBudgetInvite

    pk: Optional[str] = None
    budget_id: str = ""
    email: str = ""
    role: str = "viewer"
    invited_by_id: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_model(cls, obj: PersonalBudgetInvite):
        return cls(
            pk=_str_pk(obj.pk),
            budget_id=_fk_str(obj.budget_id),
            email=(obj.email or "").lower(),
            role=obj.role or "viewer",
            invited_by_id=_user_id_str(obj.invited_by_id),
            created_at=obj.created_at,
            updated_at=obj.updated_at,
        )

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.budget_id = data.get("budget_id", "") or ""
        o.email = (data.get("email", "") or "").lower()
        o.role = data.get("role", "viewer") or "viewer"
        o.invited_by_id = data.get("invited_by_id", "") or ""
        o.created_at = _as_datetime(data.get("created_at"))
        o.updated_at = _as_datetime(data.get("updated_at"))
        return o

    def save(self):
        if self.pk:
            obj = PersonalBudgetInvite.objects.get(pk=_int_pk(self.pk))
        else:
            obj = PersonalBudgetInvite()
        obj.budget_id = _int_pk(self.budget_id)
        obj.email = (self.email or "").lower()
        obj.role = self.role or "viewer"
        obj.invited_by_id = int(self.invited_by_id)
        obj.save()
        self.pk = _str_pk(obj.pk)
        self.email = obj.email
        self.created_at = obj.created_at
        self.updated_at = obj.updated_at
        return self

    @classmethod
    def get_for_budget_email(cls, budget_id: str, email: str):
        email = (email or "").strip().lower()
        obj = PersonalBudgetInvite.objects.filter(
            budget_id=_int_pk(budget_id),
            email__iexact=email,
        ).first()
        return cls.from_model(obj) if obj else None

    @classmethod
    def list_by_budget(cls, budget_id: str, limit: int = 200) -> List:
        qs = PersonalBudgetInvite.objects.filter(budget_id=_int_pk(budget_id)).order_by("created_at")[:limit]
        return [cls.from_model(o) for o in qs]

    @classmethod
    def list_by_email(cls, email: str, limit: int = 100) -> List:
        qs = PersonalBudgetInvite.objects.filter(email__iexact=(email or "").strip().lower()).order_by("created_at")[:limit]
        return [cls.from_model(o) for o in qs]
