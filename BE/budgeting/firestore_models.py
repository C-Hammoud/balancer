"""
Budgeting data in Firestore (Firebase). Primary data store for budgeting app.
Read/write via these models; no dependency on Django ORM for budgeting data.
"""
import logging
from decimal import Decimal
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field

from firebase_client import get_firestore_client

logger = logging.getLogger(__name__)


def _as_decimal(value):
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


def _as_date(value):
    if value is None:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _as_datetime(value):
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


class BudgetingFirestoreModel:
    collection_name: str = ""

    def __init__(self, pk: Optional[str] = None):
        self.pk = pk

    def _collection(self):
        return get_firestore_client().collection(self.collection_name)

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        raise NotImplementedError

    def save(self):
        col = self._collection()
        data = self.to_dict()
        if not self.pk:
            doc_ref = col.document()
            self.pk = doc_ref.id
            doc_ref.set(data)
        else:
            col.document(self.pk).set(data)
        return self

    def delete(self):
        if not self.pk:
            return
        self._collection().document(self.pk).delete()

    @classmethod
    def get(cls, pk: str):
        db = get_firestore_client()
        doc = db.collection(cls.collection_name).document(pk).get()
        if not doc.exists:
            return None
        return cls.from_dict(doc.id, doc.to_dict())

    @classmethod
    def list_all(cls, limit: int = 500) -> List:
        db = get_firestore_client()
        docs = db.collection(cls.collection_name).limit(limit).stream()
        return [cls.from_dict(d.id, d.to_dict()) for d in docs]

    @classmethod
    def query_by_field(cls, field_name: str, op: str, value, limit: int = 500) -> List:
        db = get_firestore_client()
        q = db.collection(cls.collection_name).where(field_name, op, value).limit(limit)
        return [cls.from_dict(d.id, d.to_dict()) for d in q.stream()]


# --- Group (user_id "" = shared default; otherwise owned by that user) ---
@dataclass
class GroupFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_groups")
    pk: Optional[str] = None
    name: str = ""
    order: int = 0
    user_id: str = ""  # "" = shared default

    def to_dict(self):
        return {"name": self.name, "order": self.order, "user_id": self.user_id or ""}

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.name = data.get("name", "") or ""
        o.order = int(data.get("order", 0) or 0)
        o.user_id = data.get("user_id", "") or ""
        return o


# --- Category (group_id = Group doc id) ---
@dataclass
class CategoryFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_categories")
    pk: Optional[str] = None
    name: str = ""
    group_id: str = ""
    include_in_reports: bool = True
    order: int = 0
    user_id: str = ""  # "" = shared default

    def to_dict(self):
        return {
            "name": self.name,
            "group_id": self.group_id,
            "include_in_reports": self.include_in_reports,
            "order": self.order,
            "user_id": self.user_id or "",
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.name = data.get("name", "") or ""
        o.group_id = data.get("group_id", "") or ""
        o.include_in_reports = bool(data.get("include_in_reports", True))
        o.order = int(data.get("order", 0) or 0)
        o.user_id = data.get("user_id", "") or ""
        return o


# --- Transaction ---
@dataclass
class TransactionFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_transactions")
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
    time: str = ""  # HH:MM
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

    def to_dict(self):
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
        now = datetime.utcnow()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        return super().save()

    @classmethod
    def list_all_for_user(cls, user_id: str) -> List:
        """Every transaction of the user (no limit): used for account balances."""
        db = get_firestore_client()
        q = db.collection(cls.collection_name).where("user_id", "==", str(user_id))
        out = [cls.from_dict(d.id, d.to_dict()) for d in q.stream()]
        out.sort(key=lambda t: (t.date or date(1970, 1, 1)))
        return out

    @classmethod
    def list_by_user(cls, user_id: str, month: Optional[str] = None, limit: int = 500) -> List:
        # Query by user_id only to avoid requiring a composite index (user_id + month + order_by date)
        db = get_firestore_client()
        q = db.collection(cls.collection_name).where("user_id", "==", str(user_id)).limit(1000)
        out = [cls.from_dict(d.id, d.to_dict()) for d in q.stream()]
        if month:
            out = [t for t in out if t.month == month]
        out.sort(key=lambda t: (t.date or date(1970, 1, 1)), reverse=True)
        return out[:limit]

    @classmethod
    def list_by_budget(cls, budget_id: str, limit: int = 2000) -> List:
        if not budget_id:
            return []
        rows = cls.query_by_field("budget_id", "==", str(budget_id), limit=limit)
        rows.sort(key=lambda t: (t.date or date(1970, 1, 1)), reverse=True)
        return rows

    @classmethod
    def exists_by_external_id(cls, user_id: str, external_id: str) -> bool:
        db = get_firestore_client()
        q = db.collection(cls.collection_name).where("user_id", "==", str(user_id)).where("external_id", "==", external_id).limit(1)
        return len(list(q.stream())) > 0

    @classmethod
    def get_by_external_id(cls, user_id: str, external_id: str):
        """Return the first transaction with this user_id and external_id, or None."""
        db = get_firestore_client()
        q = db.collection(cls.collection_name).where("user_id", "==", str(user_id)).where("external_id", "==", external_id).limit(1)
        for doc in q.stream():
            return cls.from_dict(doc.id, doc.to_dict())
        return None


# --- MerchantCategoryLink ---
@dataclass
class MerchantCategoryLinkFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_merchant_links")
    pk: Optional[str] = None
    keyword: str = ""
    category_id: str = ""
    user_id: Optional[str] = None

    def to_dict(self):
        return {"keyword": self.keyword, "category_id": self.category_id, "user_id": self.user_id}

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.keyword = data.get("keyword", "") or ""
        o.category_id = data.get("category_id", "") or ""
        o.user_id = data.get("user_id")
        return o

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 500) -> List:
        return cls.query_by_field("user_id", "==", str(user_id), limit=limit)


# --- Budget ---
@dataclass
class BudgetFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_budgets")
    pk: Optional[str] = None
    user_id: str = ""
    category_id: str = ""
    group_id: str = ""
    year: int = 0
    month: int = 0
    forecast: Decimal = Decimal("0")

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "category_id": self.category_id or "",
            "group_id": self.group_id or "",
            "year": self.year,
            "month": self.month,
            "forecast": str(self.forecast),
        }

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

    @classmethod
    def list_by_user(cls, user_id: str, year: Optional[int] = None, month: Optional[int] = None, limit: int = 1000) -> List:
        db = get_firestore_client()
        q = db.collection(cls.collection_name).where("user_id", "==", str(user_id))
        if year is not None:
            q = q.where("year", "==", year)
        if month is not None:
            q = q.where("month", "==", month)
        q = q.limit(limit)
        out = [cls.from_dict(d.id, d.to_dict()) for d in q.stream()]
        out.sort(key=lambda x: (x.year, x.month, x.group_id, x.category_id))
        return out

    @classmethod
    def get_by_user_group_month(cls, user_id: str, group_id: str, year: int, month: int):
        db = get_firestore_client()
        q = (
            db.collection(cls.collection_name)
            .where("user_id", "==", str(user_id))
            .where("group_id", "==", str(group_id))
            .where("year", "==", year)
            .where("month", "==", month)
            .limit(20)
        )
        for d in q.stream():
            row = cls.from_dict(d.id, d.to_dict())
            if not (row.category_id or "").strip():
                return row
        return None

    @classmethod
    def get_by_user_category_month(cls, user_id: str, category_id: str, year: int, month: int):
        db = get_firestore_client()
        q = (
            db.collection(cls.collection_name)
            .where("user_id", "==", str(user_id))
            .where("category_id", "==", str(category_id))
            .where("year", "==", year)
            .where("month", "==", month)
            .limit(1)
        )
        for d in q.stream():
            return cls.from_dict(d.id, d.to_dict())
        return None


# --- Savings ---
@dataclass
class SavingsFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_savings")
    pk: Optional[str] = None
    user_id: str = ""
    year: int = 0
    month: int = 0
    actual: Optional[Decimal] = None
    target: Decimal = Decimal("0")
    goal_status: str = "pending"

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "year": self.year,
            "month": self.month,
            "actual": str(self.actual) if self.actual is not None else None,
            "target": str(self.target),
            "goal_status": self.goal_status,
        }

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

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 100) -> List:
        db = get_firestore_client()
        q = db.collection(cls.collection_name).where("user_id", "==", str(user_id)).limit(limit)
        out = [cls.from_dict(d.id, d.to_dict()) for d in q.stream()]
        out.sort(key=lambda x: (x.year, x.month), reverse=True)
        return out[:limit]

    @classmethod
    def get_by_user_month(cls, user_id: str, year: int, month: int):
        db = get_firestore_client()
        q = db.collection(cls.collection_name).where("user_id", "==", str(user_id)).where("year", "==", year).where("month", "==", month).limit(1)
        for d in q.stream():
            return cls.from_dict(d.id, d.to_dict())
        return None


# --- Commitment ---
@dataclass
class CommitmentFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_commitments")
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

    def to_dict(self):
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
        now = datetime.utcnow()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        return super().save()

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 100) -> List:
        return cls.query_by_field("user_id", "==", str(user_id), limit=limit)


# --- CommitmentScheduleLine ---
@dataclass
class CommitmentScheduleLineFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_commitment_schedule_lines")
    pk: Optional[str] = None
    commitment_id: str = ""
    due_date: Optional[date] = None
    amount: Decimal = Decimal("0")
    status: str = "outstanding"  # outstanding | paid
    sequence: int = 0
    paid_date: Optional[date] = None
    reminder_sent: bool = False

    def to_dict(self):
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

    @classmethod
    def list_by_commitment(cls, commitment_id: str, limit: int = 500, *, cleanup_duplicates: bool = True) -> List:
        # Query by commitment_id only to avoid composite index (commitment_id + order_by due_date)
        db = get_firestore_client()
        q = db.collection(cls.collection_name).where("commitment_id", "==", str(commitment_id)).limit(limit)
        out = [cls.from_dict(d.id, d.to_dict()) for d in q.stream()]
        out.sort(key=lambda x: (x.due_date or date(1970, 1, 1), x.sequence))
        if cleanup_duplicates and len(out) > 1:
            out = cls._dedupe_and_cleanup(out)
        return out[:limit]

    @classmethod
    def _pick_preferred_line(cls, a, b):
        """When two lines represent the same installment, keep the best one."""
        if a.status == "paid" and b.status != "paid":
            return a, b
        if b.status == "paid" and a.status != "paid":
            return b, a
        if a.paid_date and not b.paid_date:
            return a, b
        if b.paid_date and not a.paid_date:
            return b, a
        # Stable tie-break: keep older document id
        if (a.pk or "") <= (b.pk or ""):
            return a, b
        return b, a

    @classmethod
    def _dedupe_and_cleanup(cls, lines: List) -> List:
        """
        Keep one Firestore doc per installment (by sequence, else due_date+amount).
        Deletes duplicate docs left from legacy double schedule generation.
        """
        by_seq = {}
        for line in lines:
            seq = int(line.sequence or 0)
            if seq <= 0:
                continue
            prev = by_seq.get(seq)
            if prev is None:
                by_seq[seq] = line
                continue
            keep, drop = cls._pick_preferred_line(prev, line)
            by_seq[seq] = keep
            if drop.pk and drop.pk != keep.pk:
                try:
                    drop.delete()
                except Exception as e:
                    logger.warning("Failed to delete duplicate schedule line %s: %s", drop.pk, e)

        by_due = {}
        for line in lines:
            seq = int(line.sequence or 0)
            if seq > 0:
                continue
            key = (line.due_date, str(line.amount), line.status)
            prev = by_due.get(key)
            if prev is None:
                by_due[key] = line
                continue
            keep, drop = cls._pick_preferred_line(prev, line)
            by_due[key] = keep
            if drop.pk and drop.pk != keep.pk:
                try:
                    drop.delete()
                except Exception as e:
                    logger.warning("Failed to delete duplicate schedule line %s: %s", drop.pk, e)

        merged = list(by_seq.values()) + list(by_due.values())
        merged.sort(key=lambda x: (x.due_date or date(1970, 1, 1), x.sequence))
        return merged

    @classmethod
    def delete_by_commitment(cls, commitment_id: str) -> int:
        lines = cls.list_by_commitment(commitment_id)
        for line in lines:
            line.delete()
        return len(lines)

    @classmethod
    def sum_outstanding_by_commitment(cls, commitment_id: str) -> Decimal:
        lines = cls.list_by_commitment(commitment_id)
        return sum((l.amount for l in lines if l.status == "outstanding"), Decimal("0"))

    @classmethod
    def sum_amount_due_in_month(cls, user_id: str, year: int, month: int) -> Decimal:
        start = date(year, month, 1)
        end = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
        commitments = CommitmentFS.list_by_user(user_id)
        c_ids = [c.pk for c in commitments]
        total = Decimal("0")
        for cid in c_ids:
            for line in cls.list_by_commitment(cid):
                if line.status != "outstanding":
                    continue
                if line.due_date and start <= line.due_date < end:
                    total += line.amount
        return total


# --- FinancialStanding ---
@dataclass
class FinancialStandingFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_financial_standings")
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

    def to_dict(self):
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
        if not self.created_at:
            self.created_at = datetime.utcnow()
        return super().save()

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 100) -> List:
        db = get_firestore_client()
        q = db.collection(cls.collection_name).where("user_id", "==", str(user_id)).limit(limit)
        out = [cls.from_dict(d.id, d.to_dict()) for d in q.stream()]
        out.sort(key=lambda x: x.snapshot_date or date(1970, 1, 1), reverse=True)
        return out[:limit]


# --- UploadTemplate (optional) ---
@dataclass
class UploadTemplateFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_upload_templates")
    pk: Optional[str] = None
    user_id: Optional[str] = None
    name: str = ""
    column_mapping: Dict = field(default_factory=dict)
    created_at: Optional[datetime] = None

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "name": self.name,
            "column_mapping": self.column_mapping or {},
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id")
        o.name = data.get("name", "") or ""
        o.column_mapping = data.get("column_mapping") or {}
        o.created_at = _as_datetime(data.get("created_at"))
        return o

    def save(self):
        if not self.created_at:
            self.created_at = datetime.utcnow()
        return super().save()


# --- TypeCategoryMap (expense consumption_type → budgeting category) ---
CONSUMPTION_TYPES = ("market", "transport", "food", "other")


@dataclass
class TypeCategoryMapFS(BudgetingFirestoreModel):
    """Maps expenses consumption_type to a budgeting category_id. user_id None = global default."""
    collection_name: str = field(init=False, default="budgeting_type_category_maps")
    pk: Optional[str] = None
    user_id: Optional[str] = None
    consumption_type: str = "other"
    category_id: str = ""

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "consumption_type": self.consumption_type,
            "category_id": self.category_id,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id")
        o.consumption_type = (data.get("consumption_type") or "other").lower()
        o.category_id = data.get("category_id", "") or ""
        return o

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 50) -> List:
        return cls.query_by_field("user_id", "==", str(user_id), limit=limit)

    @classmethod
    def list_global(cls, limit: int = 50) -> List:
        """Global defaults stored with user_id empty string."""
        db = get_firestore_client()
        q = db.collection(cls.collection_name).where("user_id", "==", "").limit(limit)
        return [cls.from_dict(d.id, d.to_dict()) for d in q.stream()]

    @classmethod
    def get_map_for_user(cls, user_id: str) -> Dict[str, str]:
        """Return consumption_type -> category_id; user maps override global."""
        result = {}
        for m in cls.list_global():
            if m.consumption_type:
                result[m.consumption_type] = m.category_id
        for m in cls.list_by_user(user_id):
            if m.consumption_type:
                result[m.consumption_type] = m.category_id
        return result

    @classmethod
    def get_for_user_type(cls, user_id: str, consumption_type: str):
        ctype = (consumption_type or "other").lower()
        for m in cls.list_by_user(user_id):
            if m.consumption_type == ctype:
                return m
        for m in cls.list_global():
            if m.consumption_type == ctype:
                return m
        return None


# --- BudgetThreshold ---
@dataclass
class BudgetThresholdFS(BudgetingFirestoreModel):
    """Warn/critical utilization thresholds. category_id empty = global default for user."""
    collection_name: str = field(init=False, default="budgeting_thresholds")
    pk: Optional[str] = None
    user_id: str = ""
    category_id: Optional[str] = None
    warn_pct: Decimal = Decimal("80")
    critical_pct: Decimal = Decimal("100")
    email_enabled: bool = True

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "category_id": self.category_id or "",
            "warn_pct": str(self.warn_pct),
            "critical_pct": str(self.critical_pct),
            "email_enabled": self.email_enabled,
        }

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

    @classmethod
    def list_by_user(cls, user_id: str, limit: int = 200) -> List:
        return cls.query_by_field("user_id", "==", str(user_id), limit=limit)

    @classmethod
    def get_global_for_user(cls, user_id: str):
        for t in cls.list_by_user(user_id):
            if not t.category_id:
                return t
        return None

    @classmethod
    def get_for_category(cls, user_id: str, category_id: Optional[str]):
        """Category-specific threshold if set, else user's global, else None (callers use defaults)."""
        thresholds = cls.list_by_user(user_id)
        if category_id:
            for t in thresholds:
                if t.category_id == category_id:
                    return t
        for t in thresholds:
            if not t.category_id:
                return t
        return None


# --- IncomeSource (financial accounts for transactions) ---
@dataclass
class IncomeSourceFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_income_sources")
    pk: Optional[str] = None
    user_id: str = ""
    name: str = ""
    account_type: str = "bank"
    order: int = 0
    is_active: bool = True
    is_default_for_expenses: bool = False

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "name": self.name,
            "account_type": self.account_type or "bank",
            "order": int(self.order),
            "is_active": bool(self.is_active),
            "is_default_for_expenses": bool(self.is_default_for_expenses),
        }

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

    @classmethod
    def list_by_user(cls, user_id: str, active_only: bool = False, limit: int = 200) -> List:
        rows = cls.query_by_field("user_id", "==", str(user_id), limit=limit)
        if active_only:
            rows = [r for r in rows if r.is_active]
        rows.sort(key=lambda x: (x.order, x.name.lower()))
        return rows


# --- BudgetAlert ---
@dataclass
class BudgetAlertFS(BudgetingFirestoreModel):
    collection_name: str = field(init=False, default="budgeting_alerts")
    pk: Optional[str] = None
    user_id: str = ""
    year: int = 0
    month: int = 0
    category_id: str = ""
    severity: str = "WARN"
    title: str = ""
    description: str = ""
    alert_type: str = "utilization"  # utilization | commitment_due
    utilization_pct: Optional[Decimal] = None
    actual: Decimal = Decimal("0")
    forecast: Decimal = Decimal("0")
    commitment_id: str = ""
    schedule_line_id: str = ""
    due_date: str = ""
    commitment_name: str = ""
    is_resolved: bool = False
    resolution: str = ""  # user | auto
    resolved_at: Optional[datetime] = None
    snoozed_until: Optional[datetime] = None
    email_sent: bool = False
    fingerprint: str = ""
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def to_dict(self):
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
            "commitment_due" if (data.get("category_id") or "").startswith("commitment:") else "utilization"
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
        now = datetime.utcnow()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        return super().save()

    @classmethod
    def list_by_user(cls, user_id: str, open_only: bool = False, limit: int = 200) -> List:
        out = cls.query_by_field("user_id", "==", str(user_id), limit=limit)
        if open_only:
            out = [a for a in out if not a.is_resolved]
        out.sort(key=lambda a: a.created_at or datetime.min, reverse=True)
        return out

    @classmethod
    def count_open(cls, user_id: str) -> int:
        """Open alerts that are not currently snoozed (badge count)."""
        return sum(
            1 for a in cls.list_by_user(user_id, open_only=True, limit=500)
            if not a.is_snoozed()
        )

    def is_snoozed(self, now: Optional[datetime] = None) -> bool:
        from budgeting.alert_state import alert_is_snoozed

        return alert_is_snoozed(self, now)

    @classmethod
    def get_by_fingerprint(cls, user_id: str, fingerprint: str):
        db = get_firestore_client()
        q = (
            db.collection(cls.collection_name)
            .where("user_id", "==", str(user_id))
            .where("fingerprint", "==", fingerprint)
            .limit(1)
        )
        for d in q.stream():
            return cls.from_dict(d.id, d.to_dict())
        return None

    @classmethod
    def list_for_month(cls, user_id: str, year: int, month: int, open_only: bool = False) -> List:
        out = [
            a for a in cls.list_by_user(user_id, open_only=False, limit=500)
            if a.year == year and a.month == month
        ]
        if open_only:
            out = [a for a in out if not a.is_resolved]
        return out

    @staticmethod
    def make_fingerprint(user_id: str, year: int, month: int, category_id: str, severity: str) -> str:
        return f"{user_id}|{year}|{month}|{category_id or '_'}|{severity}"


# --- UserPreferences (locale / default currency) ---
@dataclass
class UserPreferencesFS(BudgetingFirestoreModel):
    """Per-user locale preferences; document id = user_id."""
    collection_name: str = field(init=False, default="user_preferences")
    pk: Optional[str] = None
    user_id: str = ""
    timezone: str = ""
    country: str = ""
    default_currency: str = "USD"
    updated_at: Optional[datetime] = None

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "timezone": self.timezone or "",
            "country": self.country or "",
            "default_currency": self.default_currency or "USD",
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        o = cls(pk=doc_id)
        o.user_id = data.get("user_id", "") or doc_id
        o.timezone = data.get("timezone", "") or ""
        o.country = data.get("country", "") or ""
        o.default_currency = data.get("default_currency", "USD") or "USD"
        o.updated_at = _as_datetime(data.get("updated_at"))
        return o

    def save(self):
        self.updated_at = datetime.utcnow()
        if not self.pk:
            self.pk = self.user_id
        return super().save()

    @classmethod
    def get_for_user(cls, user_id: str):
        uid = str(user_id)
        return cls.get(uid)

    @classmethod
    def get_or_create(cls, user_id: str, **defaults):
        uid = str(user_id)
        existing = cls.get(uid)
        if existing:
            return existing
        prefs = cls(pk=uid, user_id=uid, **defaults)
        prefs.save()
        return prefs
