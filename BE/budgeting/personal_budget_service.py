"""Business logic for personal (multi) budgets."""
from __future__ import annotations

from decimal import Decimal
from typing import Dict, List

from django.utils import timezone

from api.currency import convert_amount
from api.utils import user_id
from budgeting.personal_budget_access import EDITOR, OWNER, require_edit, require_owner, require_view
from budgeting.personal_budget_constants import ACTIVE, ARCHIVED, DRAFT
from budgeting import sub_budgets
from budgeting.store import PersonalBudgetCategoryFS, PersonalBudgetFS, TransactionFS, GroupFS, CategoryFS


def _int_or_none(val):
    try:
        return int(val) if val not in (None, "") else None
    except (TypeError, ValueError):
        raise ValueError("Enter a whole number of months.")


def _decimal(val) -> Decimal:
    try:
        return Decimal(str(val or "0"))
    except Exception:
        return Decimal("0")


def _require_budget(user, budget_id: str) -> PersonalBudgetFS:
    budget, _role = require_view(user, budget_id)
    return budget


def _expense_total_for_budget(budget_id: str, _user, report_currency: str) -> Decimal:
    total = Decimal("0")
    for txn in TransactionFS.list_by_budget(budget_id, limit=2000):
        if txn.direction != "expense":
            continue
        total += convert_amount(txn.amount, txn.currency or "USD", report_currency)
    return total


def _expense_count_for_budget(budget_id: str) -> int:
    return sum(1 for t in TransactionFS.list_by_budget(budget_id, limit=5000) if t.direction == "expense")


def retire_default_budget(user) -> bool:
    """
    The automatic "Monthly Expenses" budget is replaced by the plan's main budget: archive it once
    and untag its transactions (they were effectively not budgeted). Safe to call repeatedly.
    """
    budget = PersonalBudgetFS.get_default_for_user(user_id(user))
    if not budget:
        return False
    for txn in TransactionFS.list_by_budget(budget.pk, limit=5000):
        txn.budget_id = ""
        txn.budget_category_id = ""
        txn.save()
    budget.is_default = False
    budget.in_plan = False
    budget.status = ARCHIVED
    budget.save()
    return True


def _spent_by_category(budget_id: str, _user, report_currency: str) -> Dict[str, Decimal]:
    out: Dict[str, Decimal] = {}
    for txn in TransactionFS.list_by_budget(budget_id, limit=2000):
        if txn.direction != "expense":
            continue
        cat_id = txn.budget_category_id or "_uncategorized_"
        out[cat_id] = out.get(cat_id, Decimal("0")) + convert_amount(
            txn.amount, txn.currency or "USD", report_currency
        )
    return out


def serialize_budget_summary(
    budget: PersonalBudgetFS,
    user,
    *,
    include_categories: bool = False,
    access_role: str | None = None,
) -> dict:
    currency = budget.currency or "USD"
    spent = _expense_total_for_budget(budget.pk, user, currency)
    total = _decimal(budget.total_amount)
    remaining = total - spent
    pct = float((spent / total * 100).quantize(Decimal("0.1"))) if total > 0 else 0.0

    data = {
        "id": budget.pk,
        "user_id": budget.user_id,
        "name": budget.name,
        "description": budget.description or "",
        "currency": currency,
        "start_date": budget.start_date.isoformat() if budget.start_date else None,
        "end_date": budget.end_date.isoformat() if budget.end_date else None,
        "total_amount": str(total),
        "status": budget.status,
        "project_tag": budget.project_tag or "",
        "notes": budget.notes or "",
        "is_default": bool(budget.is_default),
        # Sub-budget of the monthly plan: its money is reserved in the plan and its expenses count
        # only here (not in the regular category budgets).
        "in_plan": bool(getattr(budget, "in_plan", False)),
        "funding_start": budget.funding_start.isoformat() if getattr(budget, "funding_start", None) else None,
        "funding_months": int(getattr(budget, "funding_months", 1) or 1),
        "monthly_contribution": str(sub_budgets.monthly_contribution(budget).quantize(Decimal("0.01"))),
        "transactions_count": _expense_count_for_budget(budget.pk),
        "spent": str(spent.quantize(Decimal("0.01"))),
        "remaining": str(remaining.quantize(Decimal("0.01"))),
        "percent_used": pct,
        "created_at": budget.created_at.isoformat() if budget.created_at else None,
        "updated_at": budget.updated_at.isoformat() if budget.updated_at else None,
    }
    role = access_role
    if role is None:
        role = OWNER if str(budget.user_id) == user_id(user) else None
    if role:
        data["access_role"] = role
        data["is_owner"] = role == OWNER
    if include_categories:
        cats = _build_category_tree(budget.pk, user, currency)
        data["categories"] = cats
        data["categories_allocated_total"] = str(
            sum(
                _decimal(c["allocated_amount"])
                for c in cats
                if c["id"] != "_uncategorized_" and not c.get("parent_id")
            )
        )
    return data


def _serialize_category_row(cat, spent_map: Dict[str, Decimal]) -> dict:
    alloc = _decimal(cat.allocated_amount)
    cat_spent = spent_map.get(cat.pk, Decimal("0"))
    return {
        "id": cat.pk,
        "budget_id": cat.budget_id,
        "name": cat.name,
        "allocated_amount": str(alloc),
        "spent": str(cat_spent.quantize(Decimal("0.01"))),
        "remaining": str((alloc - cat_spent).quantize(Decimal("0.01"))),
        "order": cat.order,
        "notes": cat.notes or "",
        "group_id": getattr(cat, "group_id", "") or "",
        "category_id": getattr(cat, "category_id", "") or "",
        "parent_id": getattr(cat, "parent_id", "") or "",
    }


def _build_category_tree(budget_pk: str, user, currency: str) -> List[dict]:
    spent_map = _spent_by_category(budget_pk, user, currency)
    all_rows = PersonalBudgetCategoryFS.list_by_budget(budget_pk)
    by_parent: Dict[str, List[dict]] = {}
    roots: List[dict] = []
    for cat in all_rows:
        row = _serialize_category_row(cat, spent_map)
        parent_id = getattr(cat, "parent_id", "") or ""
        if parent_id:
            by_parent.setdefault(parent_id, []).append(row)
        else:
            roots.append(row)
    for root in roots:
        subs = by_parent.get(root["id"], [])
        subs.sort(key=lambda x: (x.get("order", 0), (x.get("name") or "").lower()))
        root["sub_categories"] = subs
    unc_spent = spent_map.get("_uncategorized_", Decimal("0"))
    if unc_spent > 0:
        roots.append({
            "id": "_uncategorized_",
            "budget_id": budget_pk,
            "name": "Uncategorized",
            "allocated_amount": "0",
            "spent": str(unc_spent.quantize(Decimal("0.01"))),
            "remaining": str((-unc_spent).quantize(Decimal("0.01"))),
            "order": 9999,
            "notes": "",
            "group_id": "",
            "category_id": "",
            "parent_id": "",
            "sub_categories": [],
        })
    roots.sort(key=lambda x: (x.get("order", 0), (x.get("name") or "").lower()))
    return roots


def list_personal_budgets(
    user,
    *,
    search: str = "",
    status: str = "",
    sort: str = "created_desc",
    period_start=None,
    period_end=None,
    in_plan=None,
) -> List[dict]:
    retire_default_budget(user)
    uid = user_id(user)
    rows = PersonalBudgetFS.list_by_user(uid, limit=500)
    if in_plan is not None:
        rows = [b for b in rows if bool(getattr(b, "in_plan", False)) == in_plan]
    if search:
        q = search.strip().lower()
        rows = [b for b in rows if q in (b.name or "").lower() or q in (b.description or "").lower()]
    if status:
        rows = [b for b in rows if b.status == status]
    if period_start or period_end:
        filtered = []
        for b in rows:
            b_start = b.start_date
            b_end = b.end_date
            if period_start and b_end and b_end < period_start:
                continue
            if period_end and b_start and b_start > period_end:
                continue
            filtered.append(b)
        rows = filtered
    summaries = [
        serialize_budget_summary(b, user, access_role=OWNER) for b in rows
    ]
    if sort == "name":
        summaries.sort(key=lambda x: (x["name"] or "").lower())
    elif sort == "amount":
        summaries.sort(key=lambda x: _decimal(x["total_amount"]), reverse=True)
    elif sort == "spent":
        summaries.sort(key=lambda x: _decimal(x["spent"]), reverse=True)
    elif sort == "created_asc":
        summaries.sort(key=lambda x: x.get("created_at") or "")
    else:
        summaries.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return summaries


def dashboard_summary(user) -> dict:
    from budgeting.personal_budget_sharing_service import list_shared_with_me

    budgets = list_personal_budgets(user, status="")
    shared = list_shared_with_me(user)
    active = [b for b in budgets if b["status"] not in (ARCHIVED, DRAFT)]
    total_allocated = sum(_decimal(b["total_amount"]) for b in active)
    total_spent = sum(_decimal(b["spent"]) for b in active)
    return {
        "total_budgets": len(budgets),
        "active_budgets": len(active),
        "total_allocated": str(total_allocated.quantize(Decimal("0.01"))),
        "total_spent": str(total_spent.quantize(Decimal("0.01"))),
        "total_remaining": str((total_allocated - total_spent).quantize(Decimal("0.01"))),
        "budgets": budgets,
        "shared_with_me": shared,
    }


def create_personal_budget_category(budget_id: str, user, data: dict) -> dict:
    budget, _role = require_edit(user, budget_id)
    group_id = (data.get("group_id") or "").strip()
    name = (data.get("name") or "").strip()
    if group_id and not name:
        group = GroupFS.get(group_id)
        if group:
            name = group.name
    if not name and not group_id:
        raise ValueError("Category name or group_id is required.")

    allocated = _decimal(data.get("allocated_amount", "0"))
    if group_id and allocated <= Decimal("0"):
        raise ValueError("Maximum utilization must be greater than zero.")

    # Legacy free-text category (no group link)
    if not group_id:
        cat = PersonalBudgetCategoryFS(
            budget_id=budget_id,
            name=name,
            allocated_amount=allocated,
            order=int(data.get("order", 0) or 0),
            notes=data.get("notes", "") or "",
        )
        cat.save()
        return serialize_budget_summary(budget, user, include_categories=True)

    parent = PersonalBudgetCategoryFS(
        budget_id=budget_id,
        name=name or "Category",
        allocated_amount=allocated,
        order=int(data.get("order", 0) or 0),
        notes=data.get("notes", "") or "",
        group_id=group_id,
        category_id="",
        parent_id="",
    )
    parent.save()

    subs = data.get("subcategories") or data.get("sub_categories") or []
    for idx, sub in enumerate(subs):
        amount_raw = (sub.get("allocated_amount") or "").strip()
        if not amount_raw or _decimal(amount_raw) <= Decimal("0"):
            continue
        sub_cat_id = (sub.get("category_id") or "").strip()
        sub_name = (sub.get("name") or "").strip()
        if sub_cat_id and not sub_name:
            cat_row = CategoryFS.get(sub_cat_id)
            if cat_row:
                sub_name = cat_row.name
        if not sub_name:
            continue
        PersonalBudgetCategoryFS(
            budget_id=budget_id,
            name=sub_name,
            allocated_amount=_decimal(amount_raw),
            order=int(sub.get("order", idx) or idx),
            notes=sub.get("notes", "") or "",
            group_id=group_id,
            category_id=sub_cat_id,
            parent_id=parent.pk,
        ).save()

    return serialize_budget_summary(budget, user, include_categories=True)


def create_personal_budget(user, data: dict) -> dict:
    uid = user_id(user)
    _int_or_none(data.get("funding_months"))  # a bad value is a 400 before anything is saved
    budget = PersonalBudgetFS(
        user_id=uid,
        name=data["name"],
        description=data.get("description", ""),
        currency=data.get("currency", "USD") or "USD",
        start_date=data.get("start_date"),
        end_date=data.get("end_date"),
        total_amount=_decimal(data.get("total_amount", "0")),
        status=data.get("status", DRAFT) or DRAFT,
        project_tag=data.get("project_tag", ""),
        notes=data.get("notes", ""),
    )
    budget.save()
    if data.get("in_plan"):
        # Created from the plan page as a sub-budget (raises ValueError with a user message).
        sub_budgets.attach(user, budget, _int_or_none(data.get("funding_months")), data.get("funding_start"))
    for idx, cat in enumerate(data.get("categories") or []):
        PersonalBudgetCategoryFS(
            budget_id=budget.pk,
            name=cat["name"],
            allocated_amount=_decimal(cat.get("allocated_amount", "0")),
            order=int(cat.get("order", idx)),
            notes=cat.get("notes", ""),
            group_id=cat.get("group_id", "") or "",
            category_id=cat.get("category_id", "") or "",
            parent_id=cat.get("parent_id", "") or "",
        ).save()
    return serialize_budget_summary(budget, user, include_categories=True)


def update_personal_budget(user, budget_id: str, data: dict) -> dict:
    budget, _role = require_edit(user, budget_id)
    if data.get("in_plan") is True:
        # Check before changing anything, so a refused attach leaves the budget untouched.
        error = sub_budgets.attach_error(user, budget)
        if error:
            raise ValueError(error)
        _int_or_none(data.get("funding_months"))
    for field in ("name", "description", "currency", "status", "project_tag", "notes"):
        if field in data:
            setattr(budget, field, data[field] or "")
    if "start_date" in data:
        budget.start_date = data["start_date"]
    if "end_date" in data:
        budget.end_date = data["end_date"]
    if "total_amount" in data:
        budget.total_amount = _decimal(data["total_amount"])
    budget.save()
    # Plan sub-budget: owner only; ValueError carries the message for a 400.
    if data.get("in_plan") is True or (budget.in_plan and ("funding_months" in data or "funding_start" in data)):
        sub_budgets.attach(
            user, budget,
            _int_or_none(data.get("funding_months", budget.funding_months if budget.in_plan else None)),
            data.get("funding_start", budget.funding_start if budget.in_plan else None),
        )
    elif data.get("in_plan") is False and budget.in_plan:
        sub_budgets.detach(user, budget)
    return serialize_budget_summary(budget, user, include_categories=True)


def clone_personal_budget(user, budget_id: str, data: dict) -> dict:
    source = require_owner(user, budget_id)
    payload = {
        "name": data.get("name") or f"{source.name} (copy)",
        "description": data.get("description", source.description),
        "currency": data.get("currency", source.currency),
        "start_date": data.get("start_date", source.start_date),
        "end_date": data.get("end_date", source.end_date),
        "total_amount": data.get("total_amount", source.total_amount),
        "status": data.get("status", DRAFT),
        "project_tag": data.get("project_tag", source.project_tag),
        "notes": data.get("notes", source.notes),
        "is_default": False,
        "categories": [
            {
                "name": c.name,
                "allocated_amount": c.allocated_amount,
                "order": c.order,
                "notes": c.notes,
                "group_id": getattr(c, "group_id", "") or "",
                "category_id": getattr(c, "category_id", "") or "",
                "parent_id": getattr(c, "parent_id", "") or "",
            }
            for c in PersonalBudgetCategoryFS.list_by_budget(source.pk)
        ],
    }
    return create_personal_budget(user, payload)


def budget_transactions(user, budget_id: str, limit: int = 100) -> List[dict]:
    require_view(user, budget_id)
    out = []
    for txn in TransactionFS.list_by_budget(budget_id, limit=2000):
        out.append({
            "id": txn.pk,
            "date": txn.date.isoformat() if txn.date else None,
            "description": txn.description,
            "amount": str(txn.amount),
            "currency": txn.currency,
            "direction": txn.direction,
            "budget_category_id": txn.budget_category_id or "",
            "note": txn.note or "",
        })
        if len(out) >= limit:
            break
    return out


def get_budget_detail(user, budget_id: str) -> dict:
    budget, role = require_view(user, budget_id)
    data = serialize_budget_summary(budget, user, include_categories=True, access_role=role)
    data["transactions"] = budget_transactions(user, budget_id, limit=50)
    data["can_edit"] = role in (OWNER, EDITOR)
    data["can_share"] = role == OWNER
    return data
