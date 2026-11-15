"""
E-statements exported as JSON or PDF, turned into the same rows as a CSV import:
a ["date", "description", "amount"] header, then one row per transaction with a signed amount
(negative = money out). The Java port (StatementFormats.java) follows the same rules.

JSON: the largest list of objects that have a date and an amount (at any depth). Field names are
matched loosely (bookingDate, Transaction Date, txn_date...); nested amounts such as
{"amount": {"value": "10.00", "currency": "USD"}} and debit/credit indicators are understood.

PDF (text PDFs, not scans): text is read in the order it was written (so overlapping columns don't
interleave). A transaction starts at a line beginning with a date; a few short lines after it
(a wrapped description, or the amounts printed on their own line) belong to it.
  - Running balance: when, row after row, the last amount changes by exactly one of the row's other
    amounts, the last column is a balance; the transaction amount is the other one and the balance
    change gives the direction.
  - Otherwise the transaction amount is the last non-zero amount on the row (card statements put
    fees and foreign amounts before it). Its direction comes from a CR/DR marker, a minus sign or
    brackets. Statements that mark only one side (cards mark credits "CR") make the unmarked rows
    the other side. With no markers at all, rows count as money out and are reported as uncertain.
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime, timezone
from decimal import Decimal

from budgeting.importer import HEADER_ALIASES, StatementImportError, decode_bytes, parse_amount

HEADER = ["date", "description", "amount"]


class StatementPasswordError(StatementImportError):
    """The PDF is encrypted: `code` is password_required or password_incorrect."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


# ---------------------------------------------------------------------------------------- JSON

def _norm_key(key: str) -> str:
    """bookingDate / Booking_Date / booking-date -> "booking date"."""
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", str(key))
    return " ".join(re.split(r"[\s_.\-]+", spaced.lower())).strip()


DATE_KEYS = HEADER_ALIASES["date"] | {
    "transaction date", "booking date", "value date", "date time", "datetime", "timestamp",
    "created at", "posted at", "posted date", "transaction time", "booking date time", "value date time",
}
DESCRIPTION_KEYS = HEADER_ALIASES["description"] | {
    "transaction information", "remittance information unstructured", "remittance information",
    "merchant", "merchant name", "counterparty", "counterparty name", "beneficiary", "title", "label",
    "reference", "note", "notes", "purpose", "statement description",
}
AMOUNT_KEYS = HEADER_ALIASES["amount"] | {"transaction amount", "instructed amount"}
DEBIT_KEYS = HEADER_ALIASES["debit"] | {"debit amount", "amount debit", "dr"}
CREDIT_KEYS = HEADER_ALIASES["credit"] | {"credit amount", "amount credit", "cr"}
DIRECTION_KEYS = {
    "credit debit indicator", "debit credit indicator", "type", "direction", "transaction type",
    "dr cr", "cr dr", "indicator", "debit credit", "credit debit", "sign",
}
OUT_WORDS = ("debit", "dr", "out", "expense", "withdrawal", "payment", "outgoing", "purchase", "fee")
IN_WORDS = ("credit", "cr", "in", "income", "deposit", "incoming", "refund", "salary")


def _flatten(obj: dict, prefix: str = "") -> dict:
    """{"amount": {"value": 1}} -> {"amount value": 1, "value": 1}; the first bare key wins."""
    out: dict = {}
    for key, value in obj.items():
        name = _norm_key(key)
        full = f"{prefix} {name}".strip()
        if isinstance(value, dict):
            for k, v in _flatten(value, full).items():
                out.setdefault(k, v)
            for k, v in _flatten(value).items():
                out.setdefault(k, v)
        elif not isinstance(value, list):
            out.setdefault(full, value)
            out.setdefault(name, value)
    return out


def _pick(flat: dict, keys: set[str]):
    for key in flat:
        if key in keys and flat[key] not in (None, ""):
            return flat[key]
    return None


def _nested_amount(record: dict):
    """An amount given as an object: {"amount": {"amount"/"value": ...}}."""
    for key, value in record.items():
        if _norm_key(key) in AMOUNT_KEYS and isinstance(value, dict):
            inner = {_norm_key(k): v for k, v in value.items()}
            for k in ("amount", "value", "amt"):
                if inner.get(k) not in (None, ""):
                    return inner[k]
    return None


def _looks_like_transaction(item) -> bool:
    if not isinstance(item, dict):
        return False
    flat = _flatten(item)
    has_amount = any(k in flat for k in AMOUNT_KEYS | DEBIT_KEYS | CREDIT_KEYS)
    return has_amount and any(k in flat for k in DATE_KEYS)


def _transaction_lists(node):
    if isinstance(node, list):
        if node and sum(_looks_like_transaction(i) for i in node) * 2 >= len(node):
            yield node
        for item in node:
            yield from _transaction_lists(item)
    elif isinstance(node, dict):
        for value in node.values():
            yield from _transaction_lists(value)


def _date_text(value) -> str:
    if isinstance(value, (int, Decimal)) and not isinstance(value, bool):
        seconds = int(value)
        if seconds > 10**11:  # milliseconds
            seconds //= 1000
        return datetime.fromtimestamp(seconds, tz=timezone.utc).date().isoformat()
    return str(value).strip()


def _direction_sign(value) -> int:
    words = re.split(r"[^a-z]+", str(value).lower())
    if any(w in OUT_WORDS for w in words):
        return -1
    if any(w in IN_WORDS for w in words):
        return 1
    return 0


def json_rows(raw: bytes) -> list[list[str]]:
    try:
        data = json.loads(decode_bytes(raw), parse_float=Decimal)
    except (ValueError, StatementImportError) as exc:
        raise StatementImportError("This JSON file could not be read.") from exc
    candidates = list(_transaction_lists(data))
    if not candidates:
        raise StatementImportError("No transactions found in this JSON file (each needs a date and an amount).")
    records = max(candidates, key=len)

    rows = [HEADER]
    for record in records:
        if not isinstance(record, dict):
            continue
        flat = _flatten(record)
        date_value = _pick(flat, DATE_KEYS)
        description = _pick(flat, DESCRIPTION_KEYS)
        amount = _nested_amount(record)
        if amount is None:
            amount = _pick(flat, AMOUNT_KEYS)
        amount_text = ""
        if amount is not None:
            amount_text = str(amount)
            direction = _pick(flat, DIRECTION_KEYS)
            try:
                value = parse_amount(amount_text)
            except ValueError:
                value = None
            if value is not None and value > 0 and direction is not None and _direction_sign(direction) < 0:
                amount_text = str(-value)
        else:
            debit, credit = _pick(flat, DEBIT_KEYS), _pick(flat, CREDIT_KEYS)
            try:
                if credit not in (None, "") and parse_amount(str(credit)) != 0:
                    amount_text = str(abs(parse_amount(str(credit))))
                elif debit not in (None, ""):
                    amount_text = str(-abs(parse_amount(str(debit))))
            except ValueError:
                amount_text = str(credit or debit)
        rows.append([
            _date_text(date_value) if date_value is not None else "",
            str(description or "").strip(),
            amount_text,
        ])
    return rows


# ----------------------------------------------------------------------------------------- PDF

_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7, "aug": 8,
    "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}
_MONTH_NAMES = "jan|feb|mar|apr|may|jun|jul|aug|sept|sep|oct|nov|dec"
DATE_RE = re.compile(
    r"^\s*(\d{4}-\d{1,2}-\d{1,2}"
    r"|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4}"
    rf"|\d{{1,2}}[ \-]?(?:{_MONTH_NAMES})[a-z]*[ \-,]*\d{{2,4}})(?![\d/.\-])",
    re.IGNORECASE,
)
_MONTH_DATE_RE = re.compile(rf"(\d{{1,2}})[ \-]?({_MONTH_NAMES})[a-z]*[ \-,]*(\d{{2,4}})", re.IGNORECASE)
# 1,234.56 / 1.234,56 / 1'234.56 / 12.50, optionally -, (..), or a CR/DR marker. Two decimals are
# required so reference and card numbers are not read as amounts.
AMOUNT_RE = re.compile(
    r"(?<![\w.,'])(?P<neg>-\s?)?(?P<open>\()?"
    r"(?P<num>\d{1,3}(?:[,.']\d{3})+[.,]\d{2}|\d+[.,]\d{2})"
    r"(?P<close>\))?(?P<trail>-)?(?:\s?(?P<mark>CR|DR|Cr|Dr|cr|dr)\b)?(?![\w.,]?\d)"
)
BALANCE_WORDS = (
    "opening balance", "closing balance", "balance brought forward", "balance carried forward",
    "brought forward", "carried forward", "previous balance", "balance b/f", "balance c/f",
    "starting balance", "ending balance", "beginning balance",
)
OPENING_WORDS = (
    "opening balance", "balance brought forward", "brought forward", "previous balance",
    "balance b/f", "starting balance", "beginning balance",
)
SKIP_WORDS = ("total", "subtotal", "sub total")


def _month_date_iso(text: str) -> str:
    """03 Apr 2026 / 03-APR-26 -> 2026-04-03; other date formats are returned unchanged."""
    m = _MONTH_DATE_RE.fullmatch(text.strip())
    if not m:
        return text.strip()
    day, month, year = int(m.group(1)), _MONTHS[m.group(2).lower()[:3]], int(m.group(3))
    if year < 100:
        year += 2000
    return f"{year:04d}-{month:02d}-{day:02d}"


def _signed(match: re.Match) -> tuple[Decimal, bool]:
    """(value, explicit) where explicit means the token itself said in or out."""
    value = abs(parse_amount(match.group("num")))
    mark = (match.group("mark") or "").upper()
    if match.group("neg") or (match.group("open") and match.group("close")) or match.group("trail") or mark == "DR":
        return -value, True
    if mark == "CR":
        return value, True
    return value, False


def pdf_text_lines(raw: bytes, password: str = "") -> list[str]:
    try:
        import pdfplumber
    except ImportError as exc:  # pragma: no cover - dependency listed in requirements
        raise StatementImportError("PDF import is not available on this server.") from exc
    try:
        with pdfplumber.open(io.BytesIO(raw), password=password or "") as pdf:
            lines: list[str] = []
            for page in pdf.pages:
                # Content-stream order keeps a date and an overlapping description apart; the small
                # x tolerance restores spaces that some banks don't store as characters.
                text = page.extract_text(use_text_flow=True, x_tolerance=1) or ""
                lines.extend(text.splitlines())
    except Exception as exc:
        if _is_password_error(exc):
            if password:
                raise StatementPasswordError("That password didn't open the PDF. Try again.", "password_incorrect") from exc
            raise StatementPasswordError("This PDF is password-protected. Enter its password to import it.", "password_required") from exc
        raise StatementImportError("This PDF could not be read.") from exc
    if not any(line.strip() for line in lines):
        raise StatementImportError(
            "No text found in this PDF (it may be a scanned image). Export the statement as CSV, Excel or JSON instead."
        )
    return lines


def _is_password_error(exc: BaseException) -> bool:
    seen = set()
    while exc is not None and id(exc) not in seen:
        seen.add(id(exc))
        if type(exc).__name__ in ("PDFPasswordIncorrect", "PDFEncryptionError"):
            return True
        if any(type(a).__name__ == "PDFPasswordIncorrect" for a in getattr(exc, "args", ())):
            return True
        exc = exc.__cause__ or exc.__context__
    return False


MAX_CONTINUATION_LINES = 3
CONTINUATION_MAX_CHARS = 40
CENT = Decimal("0.01")


def _split_amounts(text: str) -> tuple[str, list[tuple[Decimal, bool, str]]]:
    """(text before the first amount, [(signed value, explicit, marker)]) for one line."""
    found = list(AMOUNT_RE.finditer(text))
    head = text[: found[0].start()] if found else text
    values = []
    for m in found:
        value, explicit = _signed(m)
        values.append((value, explicit, (m.group("mark") or "").upper()))
    return head.strip(" -|:\t"), values


def _records(lines: list[str]):
    """Group lines into transactions: (date text, description, amounts) plus opening balances."""
    record = None
    extra = 0
    for line in lines:
        text = line.strip()
        if not text:
            continue
        date_match = DATE_RE.match(text)
        if date_match:
            if record:
                yield record
            rest = text[date_match.end():]
            value_date = DATE_RE.match(rest)  # posting date followed by a value date
            if value_date:
                rest = rest[value_date.end():]
            head, amounts = _split_amounts(rest)
            record = {"date": date_match.group(1), "parts": [head] if head else [], "amounts": amounts}
            extra = 0
            continue
        if record and not record["amounts"] and extra < MAX_CONTINUATION_LINES:
            head, amounts = _split_amounts(text)
            if amounts or len(text) <= CONTINUATION_MAX_CHARS:
                if head:
                    record["parts"].append(head)
                record["amounts"] = amounts
                extra += 1
                continue
        if record:
            yield record
            record = None
        if any(w in text.lower() for w in OPENING_WORDS):
            _, amounts = _split_amounts(text)
            if amounts:
                yield {"opening": amounts[-1][0]}
    if record:
        yield record


def _has_running_balance(records: list[dict]) -> bool:
    """True when each row's last amount moves by exactly one of the row's other amounts."""
    pairs = hits = 0
    previous = None
    for rec in records:
        amounts = [v for v, _, _ in rec["amounts"]]
        if len(amounts) < 2:
            previous = None
            continue
        if previous is not None:
            pairs += 1
            delta = abs(amounts[-1] - previous)
            if delta and any(abs(abs(v) - delta) < CENT for v in amounts[:-1]):
                hits += 1
        previous = amounts[-1]
    return pairs >= 2 and hits * 10 >= pairs * 6


def parse_pdf_lines(lines: list[str]) -> tuple[list[list[str]], int]:
    """(rows, uncertain): uncertain counts transactions whose direction had to be assumed."""
    items = list(_records(lines))
    records = []
    balance: Decimal | None = None
    for item in items:
        if "opening" in item:
            if not records:
                balance = item["opening"]
            continue
        description = " ".join(item["parts"]).strip()
        lower = description.lower()
        if any(w in lower for w in BALANCE_WORDS):
            if not records and any(w in lower for w in OPENING_WORDS) and item["amounts"]:
                balance = item["amounts"][-1][0]
            continue
        if not description or lower in SKIP_WORDS or not any(v for v, _, _ in item["amounts"]):
            continue
        item["description"] = description
        records.append(item)
    if not records:
        raise StatementImportError(
            "No transactions found in this PDF. Export the statement as CSV, Excel or JSON instead."
        )

    running_balance = _has_running_balance(records)
    markers = {mark for rec in records for _, _, mark in rec["amounts"] if mark}
    # Only one side marked: cards print "CR" on credits, some banks print "DR" on debits.
    unmarked_sign = -1 if markers == {"CR"} else 1 if markers == {"DR"} else None

    rows = [HEADER]
    uncertain = 0
    for rec in records:
        amounts = rec["amounts"]
        if running_balance and len(amounts) >= 2:
            new_balance = amounts[-1][0]
            nonzero = [a for a in amounts[:-1] if a[0]]
            value, explicit, _ = nonzero[0] if nonzero else amounts[0]
            if not explicit and balance is not None and abs(abs(new_balance - balance) - abs(value)) < CENT:
                value, explicit = (abs(value) if new_balance >= balance else -abs(value)), True
            balance = new_balance
        else:
            value, explicit, _ = [a for a in amounts if a[0]][-1]
        if not explicit:
            if unmarked_sign is None:
                uncertain += 1
            value = abs(value) * (unmarked_sign or -1)
        rows.append([_month_date_iso(rec["date"]), rec["description"], str(value)])
    return rows, uncertain


def pdf_rows(raw: bytes, password: str = "") -> tuple[list[list[str]], int]:
    return parse_pdf_lines(pdf_text_lines(raw, password))
