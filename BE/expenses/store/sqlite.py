"""
Django ORM-backed adapter mirroring expenses/firestore_models.py ConsumptionFS API.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, ClassVar, Dict, List, Optional, Type

from django.conf import settings
from django.db import models

from expenses.models import DjangoConsumption

DEFAULT_EXCHANGE_RATES = getattr(settings, "EXCHANGE_RATES", {"USD": 1.0})


def _as_decimal(value) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0.00")


@dataclass
class ConsumptionFS:
    pk: Optional[str] = None
    date: Optional[date] = None
    time: str = ""
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

    _model: ClassVar[Type[models.Model]] = DjangoConsumption

    def to_dict(self) -> Dict[str, Any]:
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
    def from_model(cls, obj: DjangoConsumption):
        return cls(
            pk=str(obj.pk),
            date=obj.date,
            time=(obj.time or "")[:8],
            amount=obj.amount,
            currency=obj.currency or "USD",
            amount_usd=obj.amount_usd,
            consumption_type=obj.consumption_type or "market",
            note=obj.note or "",
            country=obj.country or "",
            created_at=obj.created_at,
            created_by=str(obj.created_by_id) if obj.created_by_id else None,
            modified_at=obj.modified_at,
            modified_by=str(obj.modified_by_id) if obj.modified_by_id else None,
            record_status=obj.record_status or "active",
        )

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
            inst.created_at = (
                ca
                if isinstance(ca, datetime)
                else (datetime.fromisoformat(ca) if isinstance(ca, str) else None)
            )
        except Exception:
            inst.created_at = ca
        try:
            inst.modified_at = (
                ma
                if isinstance(ma, datetime)
                else (datetime.fromisoformat(ma) if isinstance(ma, str) else None)
            )
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
        if self.pk:
            obj = DjangoConsumption.objects.get(pk=int(self.pk))
        else:
            obj = DjangoConsumption()
        obj.date = self.date
        obj.time = (self.time or "")[:8]
        obj.amount = self.amount
        obj.currency = self.currency or "USD"
        obj.amount_usd = self.amount_usd
        obj.consumption_type = self.consumption_type or "market"
        obj.note = self.note or ""
        obj.country = self.country or ""
        obj.record_status = self.record_status or "active"
        obj.created_by_id = int(self.created_by) if self.created_by else None
        obj.modified_by_id = int(self.modified_by) if self.modified_by else None
        obj.save()
        self.pk = str(obj.pk)
        self.created_at = obj.created_at
        self.modified_at = obj.modified_at
        self.amount_usd = obj.amount_usd
        return self

    def delete(self):
        if not self.pk:
            return
        DjangoConsumption.objects.filter(pk=int(self.pk)).delete()

    @classmethod
    def get(cls, pk: str):
        try:
            obj = DjangoConsumption.objects.get(pk=int(pk))
            return cls.from_model(obj)
        except (DjangoConsumption.DoesNotExist, TypeError, ValueError):
            return None

    @classmethod
    def list(cls, limit: int = 100, start_after: Optional[str] = None) -> List:
        qs = DjangoConsumption.objects.all().order_by("-date", "-id")
        if start_after:
            try:
                after_id = int(start_after)
                qs = qs.filter(id__lt=after_id)
            except (TypeError, ValueError):
                pass
        return [cls.from_model(obj) for obj in qs[:limit]]

    @classmethod
    def query_by_field(cls, field: str, op: str, value):
        if op != "==":
            raise NotImplementedError(f"Unsupported op {op!r}")
        if field == "created_by":
            qs = DjangoConsumption.objects.filter(created_by_id=int(value))
        else:
            qs = DjangoConsumption.objects.filter(**{field: value})
        return [cls.from_model(obj) for obj in qs]
