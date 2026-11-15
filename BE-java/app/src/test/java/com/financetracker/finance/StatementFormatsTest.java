package com.financetracker.finance;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.apache.pdfbox.pdmodel.PDDocument;
import org.apache.pdfbox.pdmodel.PDPage;
import org.apache.pdfbox.pdmodel.PDPageContentStream;
import org.apache.pdfbox.pdmodel.encryption.AccessPermission;
import org.apache.pdfbox.pdmodel.encryption.StandardProtectionPolicy;
import org.apache.pdfbox.pdmodel.font.PDType1Font;
import org.apache.pdfbox.pdmodel.font.Standard14Fonts;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import com.financetracker.ApiTestSupport;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.finance.application.StatementFormats;
import com.financetracker.finance.application.StatementImporter;
import com.financetracker.finance.domain.FinanceRepositories.TransactionRepository;
import com.financetracker.finance.domain.Transaction;

/** Port of BE/tests/test_statement_formats.py. */
class StatementFormatsTest extends ApiTestSupport {

    static final String URL = B + "/transactions/upload/";

    @Autowired
    TransactionRepository transactions;

    UserAccount user;
    Api api;

    @BeforeEach
    void setUp() {
        user = makeUser();
        api = api(user);
    }

    static byte[] pdf(List<String> lines, String password) throws IOException {
        try (PDDocument doc = new PDDocument(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            PDPage page = new PDPage();
            doc.addPage(page);
            try (PDPageContentStream cs = new PDPageContentStream(doc, page)) {
                cs.setFont(new PDType1Font(Standard14Fonts.FontName.HELVETICA), 10);
                float y = 750;
                for (String line : lines) {
                    cs.beginText();
                    cs.newLineAtOffset(40, y);
                    cs.showText(line);
                    cs.endText();
                    y -= 14;
                }
            }
            if (password != null) {
                StandardProtectionPolicy policy = new StandardProtectionPolicy("owner-" + password, password,
                        new AccessPermission());
                policy.setEncryptionKeyLength(128);
                doc.protect(policy);
            }
            doc.save(out);
            return out.toByteArray();
        }
    }

    /** (date, description, amount) with the amount as a number, so 1.50 and 1.5 compare equal. */
    private static List<List<Object>> amounts(List<List<String>> rows) {
        return rows.subList(1, rows.size()).stream()
                .map(r -> List.<Object>of(r.get(0), r.get(1), new BigDecimal(r.get(2)).stripTrailingZeros()))
                .toList();
    }

    private static List<Object> row(String date, String description, String amount) {
        return List.of(date, description, new BigDecimal(amount).stripTrailingZeros());
    }

    // ---- PDF lines

    static final List<String> CARD_LINES = List.of(
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
            "8,553.15 9,575.70 -17,656.73 0.00 0.00 1.09 472.12 0.00 472.12");

    @Test
    void cardStatementLastAmountAndCrMarkers() {
        StatementFormats.Parsed p = StatementFormats.parsePdfLines(CARD_LINES);
        assertThat(amounts(p.rows())).containsExactly(
                row("01/10/2026", "Kitopi Dubai", "-175.60"),
                row("03/10/2026", "Business Falcon For SeRIY ADH 101", "-48.00"),
                row("11/10/2026", "Temu.com Dublin 4", "-360.49"),
                row("12/10/2026", "Amazon Now Riyadh", "1.50"),
                row("14/10/2026", "SADAD UTILITY BILL PAYMENT .", "-1000.00"),
                row("29/10/2026", "Payment received SABNet", "8900.00"));
        assertThat(p.uncertain()).isZero();
    }

    @Test
    void runningBalanceGivesTheDirection() {
        StatementFormats.Parsed p = StatementFormats.parsePdfLines(List.of(
                "Date Description Amount Balance",
                "Opening balance 1,000.00",
                "02/04/2026 Salary April 2,000.00 3,000.00",
                "03/04/2026 Grocery store 150.00 2,850.00",
                "05/04/2026 03/04/2026 Coffee 12.50 2,837.50",
                "06/04/2026 Refund shop 20.00 2,857.50",
                "30/04/2026 Closing balance 2,857.50"));
        assertThat(amounts(p.rows())).containsExactly(
                row("02/04/2026", "Salary April", "2000.00"),
                row("03/04/2026", "Grocery store", "-150.00"),
                row("05/04/2026", "Coffee", "-12.50"),
                row("06/04/2026", "Refund shop", "20.00"));
        assertThat(p.uncertain()).isZero();
    }

    @Test
    void signsMonthNamesAndUncertainRows() {
        StatementFormats.Parsed p = StatementFormats.parsePdfLines(List.of(
                "03 Apr 2026 Card fee 5.00",
                "04-APR-26 Transfer in 100.00",
                "2026-04-05 Ref 1234567 Withdrawal -40.00",
                "06/04/2026 Shop (25.00)"));
        assertThat(amounts(p.rows())).containsExactly(
                row("2026-04-03", "Card fee", "-5.00"),
                row("2026-04-04", "Transfer in", "-100.00"),
                row("2026-04-05", "Ref 1234567 Withdrawal", "-40.00"),
                row("06/04/2026", "Shop", "-25.00"));
        assertThat(p.uncertain()).isEqualTo(2);
    }

    @Test
    void pdfWithoutTransactionsIsExplained() {
        assertThatThrownBy(() -> StatementFormats.parsePdfLines(List.of("Statement", "Nothing to see here")))
                .isInstanceOf(StatementImporter.ImportError.class).hasMessageContaining("No transactions found");
    }

    @Test
    void pdfFileAndPasswords() throws IOException {
        List<String> lines = List.of("Trans.Date Description Amount", "01/10/2026 Kitopi Dubai 175.60",
                "02/10/2026 Refund 10.00 CR");
        StatementFormats.Parsed p = StatementFormats.pdfRows(pdf(lines, null), "");
        assertThat(p.rows().subList(1, p.rows().size()).stream().map(r -> r.get(2)))
                .containsExactly("-175.60", "10.00");
        assertThat(p.uncertain()).isZero();

        byte[] locked = pdf(lines, "s3cret");
        assertThatThrownBy(() -> StatementFormats.pdfRows(locked, ""))
                .isInstanceOfSatisfying(StatementFormats.PasswordError.class,
                        e -> assertThat(e.code()).isEqualTo("password_required"));
        assertThatThrownBy(() -> StatementFormats.pdfRows(locked, "wrong"))
                .isInstanceOfSatisfying(StatementFormats.PasswordError.class,
                        e -> assertThat(e.code()).isEqualTo("password_incorrect"));
        assertThat(StatementFormats.pdfRows(locked, "s3cret").rows()).hasSize(3);
    }

    @Test
    void pdfWithoutTextSuggestsAnotherFormat() throws IOException {
        byte[] scan;
        try (PDDocument doc = new PDDocument(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            PDPage page = new PDPage();
            doc.addPage(page);
            try (PDPageContentStream cs = new PDPageContentStream(doc, page)) {
                cs.addRect(40, 40, 100, 100); // a "scan": no text at all
                cs.fill();
            }
            doc.save(out);
            scan = out.toByteArray();
        }
        assertThatThrownBy(() -> StatementFormats.pdfRows(scan, ""))
                .isInstanceOf(StatementImporter.ImportError.class).hasMessageContaining("scanned image");
    }

    // ---- JSON

    private static List<List<String>> json(String text) {
        return StatementFormats.jsonRows(text.getBytes(StandardCharsets.UTF_8));
    }

    @Test
    void jsonOpenBankingStyle() {
        List<List<String>> rows = json("""
                {"Data": {"Transaction": [
                  {"BookingDateTime": "2026-04-03T10:00:00Z", "TransactionInformation": "Coffee shop",
                   "Amount": {"Amount": "4.50", "Currency": "SAR"}, "CreditDebitIndicator": "Debit"},
                  {"BookingDateTime": "2026-04-04T09:00:00Z", "TransactionInformation": "Salary",
                   "Amount": {"Amount": "9000.00", "Currency": "SAR"}, "CreditDebitIndicator": "Credit"}
                ]}}""");
        assertThat(rows.get(0)).isEqualTo(StatementFormats.HEADER);
        assertThat(amounts(rows)).containsExactly(
                row("2026-04-03T10:00:00Z", "Coffee shop", "-4.50"),
                row("2026-04-04T09:00:00Z", "Salary", "9000.00"));
    }

    @Test
    void jsonFlatListWithDebitCreditAndEpochDates() {
        List<List<String>> rows = json("""
                [
                  {"txn_date": "03/04/2026", "narrative": "Grocery", "debit": "150.25", "credit": ""},
                  {"txn_date": "04/04/2026", "narrative": "Refund", "debit": "", "credit": "20"},
                  {"timestamp": 1775260800000, "description": "Taxi", "amount": -12.5}
                ]""");
        assertThat(amounts(rows)).containsExactly(
                row("03/04/2026", "Grocery", "-150.25"),
                row("04/04/2026", "Refund", "20"),
                row("2026-04-04", "Taxi", "-12.5"));
    }

    @Test
    void jsonPicksTheTransactionListAmongOthers() {
        List<List<String>> rows = json("""
                {"account": {"number": "123", "holder": "A"},
                 "links": [{"rel": "self", "href": "x"}],
                 "statement": {"transactions": [
                   {"date": "2026-04-03", "description": "A", "amount": "-1.00"},
                   {"date": "2026-04-04", "description": "B", "amount": "2.00"}
                 ]}}""");
        assertThat(rows.subList(1, rows.size()).stream().map(r -> r.get(1))).containsExactly("A", "B");
    }

    @Test
    void jsonErrors() {
        assertThatThrownBy(() -> json("{not json")).hasMessageContaining("could not be read");
        assertThatThrownBy(() -> json("{\"accounts\": [{\"name\": \"x\"}]}")).hasMessageContaining("No transactions found");
    }

    // ---- upload endpoint

    @Test
    void uploadJsonAndPdf() throws IOException {
        String data = """
                [{"date": "2026-04-03", "description": "Coffee", "amount": "-4.50"},
                 {"date": "2026-04-04", "description": "Salary", "amount": "9000"}]""";
        Response r = api.upload(URL, "statement.json", data.getBytes(StandardCharsets.UTF_8));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(200);
        assertThat(r.map().get("created")).isEqualTo(2);
        assertThat(r.map().get("uncertain_direction")).isEqualTo(0);

        byte[] card = pdf(List.of("01/05/2026 Kitopi Dubai 175.60", "02/05/2026 Refund 10.00 CR"), null);
        r = api.upload(URL, "card.pdf", card);
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(200);
        assertThat(r.map().get("created")).isEqualTo(2);
        Map<String, Transaction> txns = transactions.listByUser(user.userId(), null, 100).stream()
                .collect(Collectors.toMap(t -> t.description, t -> t));
        assertThat(txns.get("Kitopi Dubai").direction).isEqualTo("expense");
        assertThat(txns.get("Kitopi Dubai").amount).isEqualByComparingTo("175.60");
        assertThat(txns.get("Refund").direction).isEqualTo("income");
        assertThat(txns.get("Salary").direction).isEqualTo("income");

        // Same file again: nothing new.
        assertThat(api.upload(URL, "card.pdf", card).map().get("created")).isEqualTo(0);
    }

    @Test
    void uploadPasswordProtectedPdf() throws IOException {
        byte[] locked = pdf(List.of("01/05/2026 Kitopi Dubai 175.60"), "s3cret");
        Response r = api.upload(URL, "card.pdf", locked);
        assertThat(r.status()).isEqualTo(400);
        assertThat(r.map().get("code")).isEqualTo("password_required");
        r = api.upload(URL, "card.pdf", locked, "password", "nope");
        assertThat(r.status()).isEqualTo(400);
        assertThat(r.map().get("code")).isEqualTo("password_incorrect");
        r = api.upload(URL, "card.pdf", locked, "password", "s3cret");
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(200);
        assertThat(r.map().get("created")).isEqualTo(1);
    }
}
