"""
Firestore models for budget planning; same interface as budgeting/store/planning_sqlite.py.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from budgeting.firestore_models import BudgetingFirestoreModel, _as_date, _as_datetime, _as_decimal


class _FsAdapter(BudgetingFirestoreModel):
    FIELDS: Dict[str, str] = {}

    def to_dict(self):
        out = {"user_id": self.user_id, "created_at": self.created_at}
        for name, kind in self.FIELDS.items():
            value = getattr(self, name)
            if kind == "dec":
                value = str(value)
            elif kind == "decn":
                value = None if value is None else str(value)
            elif kind == "date":
                value = value.isoformat() if value else None
            out[name] = value
        return out

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = str(data.get("user_id", "") or "")
        o.created_at = _as_datetime(data.get("created_at"))
        for name, kind in cls.FIELDS.items():
            if name not in data:
                continue
            value = data[name]
            if kind == "dec":
                value = _as_decimal(value)
            elif kind == "decn":
                value = None if value in (None, "") else _as_decimal(value)
            elif kind == "date":
                value = _as_date(value)
            elif kind == "dt":
                value = _as_datetime(value)
            elif kind == "int":
                value = int(value or 0)
            elif kind == "bool":
                value = bool(value)
            elif kind == "json":
                value = list(value or [])
            setattr(o, name, value)
        return o

    def save(self):
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc)
        return super().save()

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 500, **filters) -> List:
        rows = cls.query_by_field("user_id", "==", str(user_id), limit=2000)
        rows = [r for r in rows if all(getattr(r, k) == v for k, v in filters.items())]
        rows.sort(key=lambda r: r.created_at or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return rows[:limit]


@dataclass
class IncomeStreamFS(_FsAdapter):
    collection_name: str = field(init=False, default="budgeting_income_streams")
    FIELDS = {"name": "str", "amount": "dec", "currency": "str", "frequency": "str",
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
class GroupBucketFS(_FsAdapter):
    collection_name: str = field(init=False, default="budgeting_group_buckets")
    FIELDS = {"group_id": "str", "bucket": "str"}
    pk: Optional[str] = None
    user_id: str = ""
    group_id: str = ""
    bucket: str = "wants"
    created_at: Optional[datetime] = None


@dataclass
class BudgetPlanFS(_FsAdapter):
    collection_name: str = field(init=False, default="budgeting_plans")
    FIELDS = {
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
class NotificationFS(_FsAdapter):
    collection_name: str = field(init=False, default="app_notifications")
    FIELDS = {"kind": "str", "title": "str", "body": "str", "link": "str",
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
        return any(n.fingerprint == fingerprint for n in cls.list_by_user(user_id, limit=2000))


# --- Risk management ---------------------------------------------------------

from datetime import date  # noqa: E402

from budgeting.store.planning_sqlite import RISK_SETTING_FIELDS  # noqa: E402,F401  (field map shared with the ORM adapter)


@dataclass
class PlannedItemFS(_FsAdapter):
    collection_name: str = field(init=False, default="budgeting_planned_items")
    FIELDS = {
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


@dataclass
class RiskSettingsFS(_FsAdapter):
    collection_name: str = field(init=False, default="budgeting_risk_settings")
    FIELDS = RISK_SETTING_FIELDS
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
class RiskSnapshotFS(_FsAdapter):
    collection_name: str = field(init=False, default="budgeting_risk_snapshots")
    FIELDS = {"as_of": "date", "score": "intn", "level": "str", "factors": "json"}
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
        rows = [r for r in cls.list_by_user(user_id, limit=2000) if r.as_of and r.as_of >= since]
        rows.sort(key=lambda r: r.as_of)
        return rows
