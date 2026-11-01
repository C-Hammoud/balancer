from decimal import Decimal
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from firebase_client import get_firestore_client
from django.conf import settings
from dataclasses import dataclass, field

DEFAULT_EXCHANGE_RATES = getattr(settings, "EXCHANGE_RATES", {"USD": 1.0})

def _as_decimal(value):
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")

class FirestoreModel:
    collection_name: str = ""

    def __init__(self, pk: Optional[str] = None):
        self.pk = pk

    def _collection(self):
        db = get_firestore_client()
        return db.collection(self.collection_name)

    def to_dict(self) -> Dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        raise NotImplementedError

    def save(self):
        col = self._collection()
        data = self.to_dict()
        now = datetime.utcnow()
        data["created_at"] = self.created_at or now
        data["modified_at"] = self.modified_at
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
    def list(cls, limit: int = 100, start_after: Optional[str] = None) -> List:
        db = get_firestore_client()
        q = db.collection(cls.collection_name).limit(limit)
        docs = q.stream()
        return [cls.from_dict(d.id, d.to_dict()) for d in docs]

    @classmethod
    def query_by_field(cls, field: str, op: str, value):
        db = get_firestore_client()
        q = db.collection(cls.collection_name).where(field, op, value)
        docs = q.stream()
        return [cls.from_dict(d.id, d.to_dict()) for d in docs]

@dataclass
class ConsumptionFS(FirestoreModel):
    collection_name: str = field(init=False, default="consumptions")

    pk: Optional[str] = None
    date: Optional[date] = None
    time: str = ""  # HH:MM optional time of day
    amount: Decimal = Decimal("0.00")
    currency: str = "USD"
    amount_usd: Decimal = Decimal("0.00")
    consumption_type: str = "market"
    note: str = ""
    country: str = ""
    created_at: Optional[datetime] = None
    created_by: Optional[str] = None
    modified_at: Optional[datetime] = None
    modified_by: Optional[str] = None
    record_status: str = "active"

    def to_dict(self):
        return {
            "date": self.date.isoformat() if self.date else None,
            "time": (self.time or "")[:8],
            "amount": str(self.amount),
            "currency": self.currency,
            "amount_usd": str(self.amount_usd),
            "consumption_type": self.consumption_type,
            "note": self.note or "",
            "country": self.country or "",
            "created_by": self.created_by,
            "modified_by": self.modified_by,
            "record_status": self.record_status,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
        }

    @classmethod
    def from_dict(cls, doc_id: str, data: Dict[str, Any]):
        inst = cls()
        inst.pk = doc_id
        inst.date = None
        if data.get("date"):
            try:
                inst.date = date.fromisoformat(data.get("date"))
            except Exception:
                inst.date = None
        inst.time = (data.get("time") or "")[:8]
        inst.amount = _as_decimal(data.get("amount", "0"))
        inst.currency = data.get("currency", "USD")
        inst.amount_usd = _as_decimal(data.get("amount_usd", "0"))
        inst.consumption_type = data.get("consumption_type", "market")
        inst.note = data.get("note", "") or ""
        inst.country = data.get("country", "") or ""
        inst.created_by = data.get("created_by")
        inst.modified_by = data.get("modified_by")
        inst.record_status = data.get("record_status", "active")
        ca = data.get("created_at")
        ma = data.get("modified_at")
        try:
            inst.created_at = ca if isinstance(ca, datetime) else (datetime.fromisoformat(ca) if isinstance(ca, str) else None)
        except Exception:
            inst.created_at = ca
        try:
            inst.modified_at = ma if isinstance(ma, datetime) else (datetime.fromisoformat(ma) if isinstance(ma, str) else None)
        except Exception:
            inst.modified_at = ma
        return inst

    def compute_amount_usd(self):
        rates = getattr(settings, "EXCHANGE_RATES", DEFAULT_EXCHANGE_RATES)
        try:
            rate = Decimal(str(rates.get(self.currency, 1)))
        except Exception:
            rate = Decimal("1")
        self.amount_usd = (self.amount * rate).quantize(Decimal("0.01"))

    def save(self):
        if isinstance(self.amount, (str, float, int)):
            self.amount = _as_decimal(self.amount)
        self.compute_amount_usd()
        now = datetime.utcnow()
        if not self.created_at:
            self.created_at = now
        self.modified_at = now
        return super().save()