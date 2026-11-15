"""E-statements as JSON and PDF: reading rows, directions, passwords, and the upload endpoint."""
import io
import json
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from reportlab.pdfgen import canvas

from budgeting import statement_formats as sf
from budgeting.importer import StatementImportError
from budgeting.store import TransactionFS
from tests.helpers import B

URL = B + "/transactions/upload/"


def _pdf(lines, password=None) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, encrypt=password) if password else canvas.Canvas(buf)
    y = 800
    for line in lines:
        c.drawString(40, y, line)
        y -= 14
    c.save()
    return buf.getvalue()


def _amounts(rows):
    return [(r[0], r[1], Decimal(r[2])) for r in rows[1:]]


# ---- PDF lines ----

# Layout of a Saudi credit card statement: foreign amount, currency, rate, VAT, fees, then the SAR
# amount; credits end in CR; a long description wraps and its amounts move to their own line.
CARD_LINES = [
    "Credit Card Statement",
    "Trans.Date Activity/Transaction Amount (Saudi Riyals)",
    "01/10/2026 Kitopi Dubai 0.00 0.00 0.00 0.00 175.60",
    "03/10/2026 Business Falcon For SeRIY ADH",
    "101",
    "0.00 0.00 0.00 0.00 48.00",
    "11/10/2026 Temu.com Dublin 4 352.39 SAR 1.00 7.04 1.06 360.49",
    "12/10/2026 Amazon Now Riyadh 0.00 0.00 0.00 0.00 1.50 CR",
    "14/10/2026 SADAD UTILITY BILL PAYMENT . 0.00 0.00 0.00 0.00 1,000.00",
    "Please examine your card statement. In case of any error advise the bank within 30 days.",
    "29/10/2026 Payment received SABNet 0.00 0.00 8,900.00CR",
    "8,553.15 9,575.70 -17,656.73 0.00 0.00 1.09 472.12 0.00 472.12",
]


def test_card_statement_last_amount_and_cr_markers():
    rows, uncertain = sf.parse_pdf_lines(CARD_LINES)
    assert _amounts(rows) == [
        ("01/10/2026", "Kitopi Dubai", Decimal("-175.60")),
        ("03/10/2026", "Business Falcon For SeRIY ADH 101", Decimal("-48.00")),
        ("11/10/2026", "Temu.com Dublin 4", Decimal("-360.49")),
        ("12/10/2026", "Amazon Now Riyadh", Decimal("1.50")),
        ("14/10/2026", "SADAD UTILITY BILL PAYMENT .", Decimal("-1000.00")),
        ("29/10/2026", "Payment received SABNet", Decimal("8900.00")),
    ]
    assert uncertain == 0  # credits are marked, so every unmarked row is a purchase


def test_running_balance_gives_the_direction():
    rows, uncertain = sf.parse_pdf_lines([
        "Date Description Amount Balance",
        "Opening balance 1,000.00",
        "02/04/2026 Salary April 2,000.00 3,000.00",
        "03/04/2026 Grocery store 150.00 2,850.00",
        "05/04/2026 03/04/2026 Coffee 12.50 2,837.50",
        "06/04/2026 Refund shop 20.00 2,857.50",
        "30/04/2026 Closing balance 2,857.50",
    ])
    assert _amounts(rows) == [
        ("02/04/2026", "Salary April", Decimal("2000.00")),
        ("03/04/2026", "Grocery store", Decimal("-150.00")),
        ("05/04/2026", "Coffee", Decimal("-12.50")),
        ("06/04/2026", "Refund shop", Decimal("20.00")),
    ]
    assert uncertain == 0


def test_signs_month_names_and_uncertain_rows():
    rows, uncertain = sf.parse_pdf_lines([
        "03 Apr 2026 Card fee 5.00",
        "04-APR-26 Transfer in 100.00",
        "2026-04-05 Ref 1234567 Withdrawal -40.00",
        "06/04/2026 Shop (25.00)",
    ])
    assert _amounts(rows) == [
        ("2026-04-03", "Card fee", Decimal("-5.00")),
        ("2026-04-04", "Transfer in", Decimal("-100.00")),
        ("2026-04-05", "Ref 1234567 Withdrawal", Decimal("-40.00")),
        ("06/04/2026", "Shop", Decimal("-25.00")),
    ]
    assert uncertain == 2  # no balance and no markers: counted as money out, flagged


def test_pdf_without_transactions_is_explained():
    with pytest.raises(StatementImportError, match="No transactions found"):
        sf.parse_pdf_lines(["Statement", "Nothing to see here"])


def test_pdf_file_and_passwords():
    lines = ["Trans.Date Description Amount", "01/10/2026 Kitopi Dubai 175.60", "02/10/2026 Refund 10.00 CR"]
    rows, uncertain = sf.pdf_rows(_pdf(lines))
    assert [r[2] for r in rows[1:]] == ["-175.60", "10.00"] and uncertain == 0

    locked = _pdf(lines, password="s3cret")
    with pytest.raises(sf.StatementPasswordError) as exc:
        sf.pdf_rows(locked)
    assert exc.value.code == "password_required"
    with pytest.raises(sf.StatementPasswordError) as exc:
        sf.pdf_rows(locked, "wrong")
    assert exc.value.code == "password_incorrect"
    assert len(sf.pdf_rows(locked, "s3cret")[0]) == 3


def test_pdf_without_text_suggests_another_format():
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.rect(40, 40, 100, 100, fill=1)  # a "scan": no text at all
    c.save()
    with pytest.raises(StatementImportError, match="scanned image"):
        sf.pdf_rows(buf.getvalue())


# ---- JSON ----

def test_json_open_banking_style():
    data = {"Data": {"Transaction": [
        {"BookingDateTime": "2026-04-03T10:00:00Z", "TransactionInformation": "Coffee shop",
         "Amount": {"Amount": "4.50", "Currency": "SAR"}, "CreditDebitIndicator": "Debit"},
        {"BookingDateTime": "2026-04-04T09:00:00Z", "TransactionInformation": "Salary",
         "Amount": {"Amount": "9000.00", "Currency": "SAR"}, "CreditDebitIndicator": "Credit"},
    ]}}
    rows = sf.json_rows(json.dumps(data).encode())
    assert rows[0] == sf.HEADER
    assert _amounts(rows) == [
        ("2026-04-03T10:00:00Z", "Coffee shop", Decimal("-4.50")),
        ("2026-04-04T09:00:00Z", "Salary", Decimal("9000.00")),
    ]


def test_json_flat_list_with_debit_credit_and_epoch_dates():
    data = [
        {"txn_date": "03/04/2026", "narrative": "Grocery", "debit": "150.25", "credit": ""},
        {"txn_date": "04/04/2026", "narrative": "Refund", "debit": "", "credit": "20"},
        {"timestamp": 1775260800000, "description": "Taxi", "amount": -12.5},
    ]
    assert _amounts(sf.json_rows(json.dumps(data).encode())) == [
        ("03/04/2026", "Grocery", Decimal("-150.25")),
        ("04/04/2026", "Refund", Decimal("20")),
        ("2026-04-04", "Taxi", Decimal("-12.5")),
    ]


def test_json_picks_the_transaction_list_among_others():
    data = {
        "account": {"number": "123", "holder": "A"},
        "links": [{"rel": "self", "href": "x"}],
        "statement": {"transactions": [
            {"date": "2026-04-03", "description": "A", "amount": "-1.00"},
            {"date": "2026-04-04", "description": "B", "amount": "2.00"},
        ]},
    }
    assert [r[1] for r in sf.json_rows(json.dumps(data).encode())[1:]] == ["A", "B"]


def test_json_errors():
    with pytest.raises(StatementImportError, match="could not be read"):
        sf.json_rows(b"{not json")
    with pytest.raises(StatementImportError, match="No transactions found"):
        sf.json_rows(b'{"accounts": [{"name": "x"}]}')


# ---- upload endpoint ----

@pytest.mark.django_db
def test_upload_json_and_pdf(api, user):
    data = [
        {"date": "2026-04-03", "description": "Coffee", "amount": "-4.50"},
        {"date": "2026-04-04", "description": "Salary", "amount": "9000"},
    ]
    r = api.post(URL, {"file": SimpleUploadedFile("statement.json", json.dumps(data).encode())}, format="multipart")
    assert r.status_code == 200, r.content
    assert r.json()["created"] == 2 and r.json()["uncertain_direction"] == 0

    pdf = _pdf(["01/05/2026 Kitopi Dubai 175.60", "02/05/2026 Refund 10.00 CR"])
    r = api.post(URL, {"file": SimpleUploadedFile("card.pdf", pdf)}, format="multipart")
    assert r.status_code == 200, r.content
    assert r.json()["created"] == 2
    txns = {t.description: t for t in TransactionFS.list_by_user(str(user.pk), limit=100)}
    assert txns["Kitopi Dubai"].direction == "expense" and txns["Kitopi Dubai"].amount == Decimal("175.60")
    assert txns["Refund"].direction == "income"
    assert txns["Salary"].direction == "income"

    # Same file again: nothing new.
    r = api.post(URL, {"file": SimpleUploadedFile("card.pdf", pdf)}, format="multipart")
    assert r.json()["created"] == 0


@pytest.mark.django_db
def test_upload_password_protected_pdf(api):
    locked = _pdf(["01/05/2026 Kitopi Dubai 175.60"], password="s3cret")
    r = api.post(URL, {"file": SimpleUploadedFile("card.pdf", locked)}, format="multipart")
    assert r.status_code == 400 and r.json()["code"] == "password_required"
    r = api.post(URL, {"file": SimpleUploadedFile("card.pdf", locked), "password": "nope"}, format="multipart")
    assert r.status_code == 400 and r.json()["code"] == "password_incorrect"
    r = api.post(URL, {"file": SimpleUploadedFile("card.pdf", locked), "password": "s3cret"}, format="multipart")
    assert r.status_code == 200 and r.json()["created"] == 1
