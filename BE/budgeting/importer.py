"""
Bank statement import: read CSV/XLSX rows, detect columns, parse dates and amounts.
Pure functions (no store access) so the parsing rules are easy to test.
"""
import csv
import io
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

DATE_FORMATS = ("auto", "dmy", "mdy", "ymd")
# Countries whose banks export month-first dates; everyone else defaults to day-first.
MONTH_FIRST_COUNTRIES = {"US", "PH", "FM", "PW", "MH"}

HEADER_ALIASES = {
    "date": {"date", "txn_date", "transaction date", "txn date", "posted", "posting date",
             "value date", "booking date"},
    "description": {"description", "desc", "memo", "details", "payee", "narrative", "name",
                    "transaction details", "particulars", "remarks"},
    "amount": {"amount", "amt", "value", "sum", "transaction amount"},
    "debit": {"debit", "withdrawal", "withdrawals", "debit amount", "money out", "paid out"},
    "credit": {"credit", "deposit", "deposits", "credit amount", "money in", "paid in"},
}


class StatementImportError(ValueError):
    """Raised for a file the importer cannot read (shown to the user)."""


def default_date_format(country: str | None) -> str:
    return "mdy" if (country or "").upper() in MONTH_FIRST_COUNTRIES else "dmy"


def decode_bytes(raw: bytes) -> str:
    """Decode once from the bytes already read; try UTF-8, Arabic Windows, then Latin-1."""
    for enc in ("utf-8-sig", "cp1256", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise StatementImportError("Could not read the file's text encoding. Save it as UTF-8 CSV and try again.")


def _cell_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value).strip()


def read_rows(filename: str, raw: bytes) -> list[list[str]]:
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        try:
            from openpyxl import load_workbook
        except ImportError as exc:  # pragma: no cover - dependency listed in requirements
            raise StatementImportError("Excel import is not available on this server.") from exc
        try:
            wb = load_workbook(io.BytesIO(raw), read_only=True, data_only=True)
        except Exception as exc:
            raise StatementImportError("Could not open the Excel file.") from exc
        ws = wb.worksheets[0]
        rows = [[_cell_str(v) for v in row] for row in ws.iter_rows(values_only=True)]
        wb.close()
        return rows
    if name.endswith(".csv"):
        text = decode_bytes(raw)
        sample = text[:4096]
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        return [list(r) for r in csv.reader(io.StringIO(text), dialect)]
    raise StatementImportError("Upload a .csv or .xlsx file.")


def column_map(header_row) -> dict | None:
    """Map known header names to indices. Returns None if the row is not a header."""
    cells = [(c or "").strip().lower() for c in header_row]
    mapping = {}
    for field, names in HEADER_ALIASES.items():
        for i, cell in enumerate(cells):
            if cell in names:
                mapping[field] = i
                break
    has_amount = "amount" in mapping or "debit" in mapping or "credit" in mapping
    if "date" in mapping and "description" in mapping and has_amount:
        return mapping
    if cells and cells[0] in HEADER_ALIASES["date"]:
        return {"date": 0, "description": 1, "amount": 2}
    return None


def parse_amount(raw: str) -> Decimal:
    """
    Accepts 1,234.56 / 1.234,56 / (12.50) / 12.50- / currency symbols or codes.
    Raises ValueError if no number can be read.
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty amount")
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative, s = True, s[1:-1]
    if s.endswith("-"):
        negative, s = True, s[:-1]
    # Keep only the number itself: currency symbols around it may contain dots
    # (e.g. the riyal sign "ر.س") that must not be read as decimal separators.
    digits = [i for i, ch in enumerate(s) if ch.isdigit()]
    if not digits:
        raise ValueError(f"bad amount {raw!r}")
    if "-" in s[: digits[0]]:
        negative = not negative
    s = "".join(ch for ch in s[digits[0] : digits[-1] + 1] if ch.isdigit() or ch in ",.")
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")  # 1.234,56
        else:
            s = s.replace(",", "")  # 1,234.56
    elif "," in s:
        head, _, tail = s.rpartition(",")
        # "12,5" / "12,50" = decimal comma; "1,234" = thousands
        s = f"{head.replace(',', '')}.{tail}" if 1 <= len(tail) <= 2 else s.replace(",", "")
    try:
        value = Decimal(s)
    except InvalidOperation as exc:
        raise ValueError(f"bad amount {raw!r}") from exc
    return -value if negative else value


def parse_date(raw: str, date_format: str = "dmy") -> date:
    """
    ISO (YYYY-MM-DD) is always accepted. Other dates use / - or . separators:
      dmy = 03/04/2026 is 3 April (Lebanon, Saudi Arabia, most of the world)
      mdy = 03/04/2026 is 4 March (US)
      ymd = 2026/04/03
      auto = use a part greater than 12 to decide, otherwise fall back to dmy
    Two-digit years are read as 20YY.
    """
    s = (raw or "").strip()
    if not s:
        raise ValueError("empty date")
    head = s[:10]
    if len(head) == 10 and head[4] == "-" and head[7] == "-":
        return date.fromisoformat(head)
    s = s.split(" ")[0].split("T")[0]
    for sep in ("/", "-", "."):
        if sep in s:
            parts = s.split(sep)
            break
    else:
        raise ValueError(f"unrecognised date {raw!r}")
    if len(parts) != 3 or not all(p.strip().isdigit() for p in parts):
        raise ValueError(f"unrecognised date {raw!r}")
    a, b, c = (int(p) for p in parts)
    if date_format == "ymd" or len(parts[0].strip()) == 4:
        return date(a, b, c)
    year = c + 2000 if c < 100 else c
    if date_format == "mdy":
        return date(year, a, b)
    if date_format == "auto":
        if a > 12 >= b:
            return date(year, b, a)
        if b > 12 >= a:
            return date(year, a, b)
    return date(year, b, a)  # dmy (default for auto when ambiguous)


def guess_date_format(date_strings, fallback: str) -> str:
    """Pick dmy/mdy from the file itself when any date has a day above 12."""
    for raw in date_strings:
        s = (raw or "").strip().split(" ")[0]
        for sep in ("/", "-", "."):
            if sep in s:
                parts = s.split(sep)
                break
        else:
            continue
        if len(parts) != 3 or not all(p.isdigit() for p in parts) or len(parts[0]) == 4:
            continue
        a, b = int(parts[0]), int(parts[1])
        if a > 12 >= b:
            return "dmy"
        if b > 12 >= a:
            return "mdy"
    return fallback


def extract_fields(row, col_map: dict | None):
    """Return (date_str, description, amount_str) for one row; raises IndexError if short."""
    def cell(key, default_idx=None):
        idx = col_map.get(key, default_idx) if col_map else default_idx
        if idx is None or idx >= len(row):
            return ""
        return (row[idx] or "").strip()

    if not col_map:
        return row[0].strip(), row[1].strip(), row[2].strip()
    amount = cell("amount")
    if not amount and ("debit" in col_map or "credit" in col_map):
        debit, credit = cell("debit"), cell("credit")
        if credit and parse_amount(credit) != 0:
            amount = str(abs(parse_amount(credit)))
        elif debit:
            amount = str(-abs(parse_amount(debit)))
    return cell("date"), cell("description"), amount


def dedupe_key(txn_date: date, amount: Decimal, description: str, occurrence: int) -> str:
    """
    Stable id for an imported row. `occurrence` counts identical rows within one file, so
    two genuine same-day coffees both import, while re-uploading the file adds nothing.
    """
    base = f"{txn_date.isoformat()}|{amount}|{description[:100]}"
    return base if occurrence <= 1 else f"{base}#{occurrence}"
