"""
Commitment payment schedules and due-date reminder emails.
"""
import calendar
import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.contrib.auth import get_user_model

from .store import CommitmentFS, CommitmentScheduleLineFS
from .services import _user_id

logger = logging.getLogger(__name__)

FREQ_MONTHS = {
    "monthly": 1,
    "quarterly": 3,
    "yearly": 12,
}


def add_months(d: date, months: int) -> date:
    """Add calendar months, clamping day to last day of target month."""
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    last = calendar.monthrange(y, m)[1]
    return date(y, m, min(d.day, last))


def payment_count(term_months: int, frequency: str) -> int:
    step = FREQ_MONTHS.get(frequency or "monthly", 1)
    term = max(int(term_months or 0), 0)
    if term <= 0:
        return 1
    return max((term + step - 1) // step, 1)


def generate_schedule_lines(commitment: CommitmentFS, *, replace: bool = False) -> list:
    """
    Build installment lines from start_date / term / frequency / payment_amount.
    Balloon (if any) is added to the final installment.
    If replace=False and a full schedule exists, returns existing lines.
    Otherwise rebuilds the schedule. Paid installments are always kept (payment history
    and their transactions stay linked); only outstanding lines are recreated.
    """
    if not commitment or not commitment.pk:
        return []
    existing = CommitmentScheduleLineFS.list_by_commitment(commitment.pk)
    expected = payment_count(commitment.term_months, commitment.frequency)
    if existing and not replace and len(existing) >= expected:
        return existing

    paid_by_seq = {}
    paid_extra = []  # paid duplicates of a sequence: never delete payment history
    for line in existing:
        if line.status != "paid":
            line.delete()
        elif line.sequence in paid_by_seq:
            paid_extra.append(line)
        else:
            paid_by_seq[line.sequence] = line

    if not commitment.start_date or commitment.payment_amount <= 0:
        return sorted([*paid_by_seq.values(), *paid_extra], key=lambda l: l.sequence)

    step = FREQ_MONTHS.get(commitment.frequency or "monthly", 1)
    balloon = commitment.balloon or Decimal("0")
    lines = []
    for i in range(expected):
        seq = i + 1
        if seq in paid_by_seq:
            lines.append(paid_by_seq.pop(seq))
            continue
        amt = commitment.payment_amount
        if i == expected - 1 and balloon > 0:
            amt = amt + balloon
        line = CommitmentScheduleLineFS(
            commitment_id=commitment.pk,
            due_date=add_months(commitment.start_date, i * step),
            amount=amt,
            status="outstanding",
            sequence=seq,
            paid_date=None,
            reminder_sent=False,
        )
        line.save()
        lines.append(line)
    # Paid lines beyond a shortened term are kept, not dropped.
    lines.extend(paid_by_seq.values())
    lines.extend(paid_extra)
    lines.sort(key=lambda l: (l.sequence, l.due_date or date.min))
    return lines


def ensure_schedule(commitment: CommitmentFS) -> list:
    """Generate schedule if missing (for legacy commitments)."""
    return generate_schedule_lines(commitment, replace=False)


def schedule_progress(commitment: CommitmentFS) -> dict:
    """Counts, remaining principal, next due, and line list."""
    lines = ensure_schedule(commitment)
    total = len(lines)
    paid = [l for l in lines if l.status == "paid"]
    outstanding = [l for l in lines if l.status == "outstanding"]
    next_due = outstanding[0] if outstanding else None
    today = date.today()
    upcoming = [
        l for l in outstanding
        if l.due_date and l.due_date >= today
    ]
    overdue = [
        l for l in outstanding
        if l.due_date and l.due_date < today
    ]
    return {
        "lines": lines,
        "payments_total": total,
        "payments_completed": len(paid),
        "payments_remaining": len(outstanding),
        "remaining_principal": sum((l.amount for l in outstanding), Decimal("0")),
        "next_due_date": next_due.due_date.isoformat() if next_due and next_due.due_date else None,
        "next_due_amount": next_due.amount if next_due else Decimal("0"),
        "next_due_line_id": next_due.pk if next_due else None,
        "upcoming_count": len(upcoming),
        "overdue_count": len(overdue),
    }


def line_to_dict(line: CommitmentScheduleLineFS) -> dict:
    today = date.today()
    due = line.due_date
    payment = line.paid_date
    is_overdue = bool(line.status == "outstanding" and due and due < today)
    days_until = (due - today).days if due and line.status == "outstanding" else None
    return {
        "id": line.pk,
        "commitment_id": line.commitment_id,
        "sequence": line.sequence,
        "due_date": due.isoformat() if due else None,
        "payment_date": payment.isoformat() if payment else None,
        "paid_date": payment.isoformat() if payment else None,  # alias
        "amount": line.amount,
        "status": line.status,
        "reminder_sent": bool(line.reminder_sent),
        "is_overdue": is_overdue,
        "days_until_due": days_until,
    }


def mark_line_paid(line: CommitmentScheduleLineFS, paid_date: Optional[date] = None) -> CommitmentScheduleLineFS:
    line.status = "paid"
    line.paid_date = paid_date or date.today()
    line.save()
    return line


def mark_line_outstanding(line: CommitmentScheduleLineFS) -> CommitmentScheduleLineFS:
    line.status = "outstanding"
    line.paid_date = None
    line.reminder_sent = False
    line.save()
    return line


def line_external_id(line_id: str) -> str:
    return f"commitment_line:{line_id}"


def record_line_payment(
    user,
    commitment: CommitmentFS,
    line: CommitmentScheduleLineFS,
    paid_date: Optional[date] = None,
    *,
    category_id: Optional[str] = None,
    account=None,
):
    """
    Mark an installment paid AND record its expense transaction (one flow).
    Without this, a paid line drops out of "commitments due" but no expense replaces it,
    so savings would rise by the installment amount.
    Returns (line, transaction). Reuses an existing linked transaction if present.
    """
    from datetime import datetime

    from .store import TransactionFS

    uid = _user_id(user)
    paid_date = paid_date or date.today()
    ext_id = line_external_id(line.pk)
    txn = TransactionFS.get_by_external_id(uid, ext_id)
    if not txn:
        txn = TransactionFS(
            user_id=uid,
            date=paid_date,
            month=paid_date.strftime("%Y-%m"),
            description=(commitment.name or "Commitment")[:500],
            category_id=category_id or None,
            classification=None,
            amount=line.amount,
            currency=getattr(commitment, "currency", None) or "USD",
            note=f"Commitment payment — {commitment.name}",
            time=datetime.now().strftime("%H:%M"),
            direction="expense",
            source_account=account.name if account else "",
            income_source_id=account.pk if account else "",
            commitment_id=commitment.pk,
            schedule_line_id=line.pk,
            external_id=ext_id,
            # Counted in a category budget only when the user picked a category.
            include_in_utilization=bool(category_id),
        )
        txn.save()
    mark_line_paid(line, paid_date)
    return line, txn


def reverse_line_payment(user, line: CommitmentScheduleLineFS):
    """Mark an installment outstanding again and delete its linked expense transaction."""
    from .store import TransactionFS

    txn = TransactionFS.get_by_external_id(_user_id(user), line_external_id(line.pk))
    if txn:
        txn.delete()
    return mark_line_outstanding(line)


def sync_payment_date(user, line: CommitmentScheduleLineFS) -> None:
    """Keep the linked transaction's date and amount in step when a paid line is edited."""
    from .store import TransactionFS

    txn = TransactionFS.get_by_external_id(_user_id(user), line_external_id(line.pk))
    if not txn:
        return
    changed = False
    if line.paid_date and txn.date != line.paid_date:
        txn.date = line.paid_date
        txn.month = line.paid_date.strftime("%Y-%m")
        changed = True
    if txn.amount != line.amount:
        txn.amount = line.amount
        changed = True
    if changed:
        txn.save()


def evaluate_commitment_reminders(user=None) -> int:
    """
    Email reminders for outstanding installments within each commitment's
    reminder_days_before window. Marks reminder_sent so each line emails once.
    If user is None, process all users who have commitments.
    Returns number of emails attempted/sent.
    """
    User = get_user_model()
    sent = 0
    today = date.today()

    if user is not None:
        users = [user]
    else:
        # Unique user ids from commitments
        all_c = CommitmentFS.list_all(limit=2000)
        uids = sorted({c.user_id for c in all_c if c.user_id})
        users = []
        for uid in uids:
            try:
                users.append(User.objects.get(pk=int(uid)))
            except Exception:
                try:
                    users.append(User.objects.get(pk=uid))
                except Exception:
                    logger.info("Skip reminders for unknown user_id=%s", uid)

    for u in users:
        uid = _user_id(u)
        for c in CommitmentFS.list_by_user(uid):
            if not c.reminder_enabled:
                continue
            days_before = max(int(c.reminder_days_before or 0), 0)
            lines = ensure_schedule(c)
            for line in lines:
                if line.status != "outstanding" or not line.due_date or line.reminder_sent:
                    continue
                # Notify from (due - days_before) through due date (inclusive)
                window_start = line.due_date - timedelta(days=days_before)
                if window_start <= today <= line.due_date:
                    if _send_commitment_reminder_email(u, c, line):
                        line.reminder_sent = True
                        line.save()
                        sent += 1
    return sent


def _send_commitment_reminder_email(user, commitment: CommitmentFS, line: CommitmentScheduleLineFS) -> bool:
    from api.emails import send_commitment_reminder_email

    email = getattr(user, "email", None) or ""
    if not email:
        logger.info(
            "No email for user %s; skipping commitment reminder %s/%s",
            getattr(user, "pk", "?"),
            commitment.pk,
            line.pk,
        )
        return False
    due = line.due_date.isoformat() if line.due_date else "—"
    try:
        return send_commitment_reminder_email(
            user=user,
            commitment_name=commitment.name,
            due_date=due,
            amount=str(line.amount),
            sequence=int(line.sequence or 0),
        )
    except Exception as e:
        logger.warning("Failed to send commitment reminder email: %s", e)
        return False
