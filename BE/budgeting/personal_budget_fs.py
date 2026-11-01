"""Firestore models for user-owned personal budgets (multi-budget feature)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from budgeting.firestore_models import BudgetingFirestoreModel, _as_date, _as_datetime, _as_decimal
from budgeting.personal_budget_constants import DRAFT


@dataclass
class PersonalBudgetFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_personal_budgets")
    pk: Optional[str] = None
    user_id: str = ""
    name: str = ""
    description: str = ""
    currency: str = "USD"
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    total_amount: Decimal = Decimal("0")
    status: str = DRAFT
    project_tag: str = ""
    notes: str = ""
    is_default: bool = False
    in_plan: bool = False
    funding_start: Optional[date] = None
    funding_months: int = 1
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "name": self.name,
            "description": self.description or "",
            "currency": self.currency or "USD",
            "start_date": self.start_date.isoformat() if self.start_date else None,
            "end_date": self.end_date.isoformat() if self.end_date else None,
            "total_amount": str(self.total_amount),
            "status": self.status or DRAFT,
            "project_tag": self.project_tag or "",
            "notes": self.notes or "",
            "is_default": bool(self.is_default),
            "in_plan": bool(self.in_plan),
            "funding_start": self.funding_start.isoformat() if self.funding_start else None,
            "funding_months": max(1, int(self.funding_months or 1)),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

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
        o.status = data.get("status", DRAFT) or DRAFT
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
        now = datetime.utcnow()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        return super().save()

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 500) -> List:
        rows = cls.query_by_field("user_id", "==", str(user_id), limit=limit)
        rows.sort(key=lambda b: (not b.is_default, b.name.lower()))
        return rows

    @classmethod
    def get_default_for_user(cls, user_id: str):
        for row in cls.list_by_user(user_id, limit=100):
            if row.is_default:
                return row
        return None


@dataclass
class PersonalBudgetMemberFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_personal_budget_members")
    pk: Optional[str] = None
    budget_id: str = ""
    user_id: str = ""
    role: str = "viewer"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "budget_id": self.budget_id,
            "user_id": self.user_id,
            "role": self.role or "viewer",
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

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
        now = datetime.utcnow()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        return super().save()

    @classmethod
    def get_for_budget_user(cls, budget_id: str, user_id: str):
        for row in cls.list_by_budget(budget_id, limit=500):
            if str(row.user_id) == str(user_id):
                return row
        return None

    @classmethod
    def list_by_budget(cls, budget_id: str, limit: int = 200) -> List:
        rows = cls.query_by_field("budget_id", "==", str(budget_id), limit=limit)
        rows.sort(key=lambda m: m.created_at or datetime.min)
        return rows

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 500) -> List:
        rows = cls.query_by_field("user_id", "==", str(user_id), limit=limit)
        rows.sort(key=lambda m: m.created_at or datetime.min, reverse=True)
        return rows


@dataclass
class PersonalBudgetNotificationFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_personal_budget_notifications")
    pk: Optional[str] = None
    recipient_id: str = ""
    budget_id: str = ""
    shared_by_id: str = ""
    role: str = "viewer"
    title: str = ""
    message: str = ""
    read_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "recipient_id": self.recipient_id,
            "budget_id": self.budget_id,
            "shared_by_id": self.shared_by_id,
            "role": self.role or "viewer",
            "title": self.title,
            "message": self.message or "",
            "read_at": self.read_at,
            "created_at": self.created_at,
        }

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
        if not self.created_at:
            self.created_at = datetime.utcnow()
        return super().save()

    @classmethod
    def list_for_recipient(cls, user_id: str, limit: int = 100) -> List:
        rows = cls.query_by_field("recipient_id", "==", str(user_id), limit=limit)
        rows.sort(key=lambda n: n.created_at or datetime.min, reverse=True)
        return rows


@dataclass
class PersonalBudgetInviteFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_personal_budget_invites")
    pk: Optional[str] = None
    budget_id: str = ""
    email: str = ""
    role: str = "viewer"
    invited_by_id: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "budget_id": self.budget_id,
            "email": (self.email or "").lower(),
            "role": self.role or "viewer",
            "invited_by_id": self.invited_by_id,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

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
        now = datetime.utcnow()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        self.email = (self.email or "").lower()
        return super().save()

    @classmethod
    def get_for_budget_email(cls, budget_id: str, email: str):
        email = (email or "").strip().lower()
        for row in cls.list_by_budget(budget_id, limit=200):
            if row.email == email:
                return row
        return None

    @classmethod
    def list_by_budget(cls, budget_id: str, limit: int = 200) -> List:
        rows = cls.query_by_field("budget_id", "==", str(budget_id), limit=limit)
        rows.sort(key=lambda r: r.created_at or datetime.min)
        return rows

    @classmethod
    def list_by_email(cls, email: str, limit: int = 100) -> List:
        email = (email or "").strip().lower()
        rows = cls.query_by_field("email", "==", email, limit=limit)
        return rows


@dataclass
class PersonalBudgetCategoryFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_personal_budget_categories")
    pk: Optional[str] = None
    budget_id: str = ""
    name: str = ""
    allocated_amount: Decimal = Decimal("0")
    order: int = 0
    notes: str = ""
    group_id: str = ""
    category_id: str = ""
    parent_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "budget_id": self.budget_id,
            "name": self.name,
            "allocated_amount": str(self.allocated_amount),
            "order": int(self.order or 0),
            "notes": self.notes or "",
            "group_id": self.group_id or "",
            "category_id": self.category_id or "",
            "parent_id": self.parent_id or "",
        }

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

    @classmethod
    def list_by_budget(cls, budget_id: str, limit: int = 200) -> List:
        rows = cls.query_by_field("budget_id", "==", str(budget_id), limit=limit)
        rows.sort(key=lambda c: (c.order, c.name.lower()))
        return rows
