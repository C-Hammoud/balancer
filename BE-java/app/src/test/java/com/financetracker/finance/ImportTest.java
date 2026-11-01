package com.financetracker.finance;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.ByteArrayOutputStream;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.apache.poi.ss.usermodel.CellStyle;
import org.apache.poi.ss.usermodel.Row;
import org.apache.poi.ss.usermodel.Sheet;
import org.apache.poi.xssf.usermodel.XSSFWorkbook;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.springframework.beans.factory.annotation.Autowired;

import com.financetracker.ApiTestSupport;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.finance.application.StatementImporter;
import com.financetracker.finance.domain.FinanceRepositories.TransactionRepository;
import com.financetracker.finance.domain.Transaction;
import com.financetracker.shared.config.AppProperties;

/** Port of BE/tests/test_import.py. */
class ImportTest extends ApiTestSupport {

    static final String URL = B + "/transactions/upload/";

    @Autowired
    TransactionRepository transactions;
    @Autowired
    AppProperties props;

    UserAccount user;
    Api api;

    @BeforeEach
    void setUp() {
        user = makeUser();
        api = api(user);
    }

    private Response upload(String csv, String... fields) {
        return api.upload(URL, "statement.csv", csv.getBytes(StandardCharsets.UTF_8), fields);
    }

    private List<Transaction> txns() {
        return transactions.listByUser(user.userId(), null, 1000).stream()
                .sorted(Comparator.comparing((Transaction t) -> t.date).thenComparing(t -> t.description)).toList();
    }

    // ---- pure parsing

    @ParameterizedTest
    @CsvSource({
            "03/04/2026, dmy, 2026-04-03",
            "03/04/2026, mdy, 2026-03-04",
            "2026-04-03, mdy, 2026-04-03",
            "03.04.26, dmy, 2026-04-03",
            "13/04/2026, auto, 2026-04-13",
            "04/13/2026, auto, 2026-04-13",
            "2026/04/03, dmy, 2026-04-03",
    })
    void parseDate(String raw, String fmt, String expected) {
        assertThat(StatementImporter.parseDate(raw, fmt)).isEqualTo(LocalDate.parse(expected));
    }

    @ParameterizedTest
    @CsvSource(delimiter = '|', value = {
            "1,234.56|1234.56", "1.234,56|1234.56", "(12.50)|-12.50", "-SAR 45|-45", "50-|-50",
            "12,5|12.5", "1,234|1234", "ر.س 20|20",
    })
    void parseAmount(String raw, String expected) {
        assertThat(StatementImporter.parseAmount(raw)).isEqualByComparingTo(expected);
    }

    @Test
    void defaultDateFormatByCountry() {
        assertThat(StatementImporter.defaultDateFormat("LB")).isEqualTo("dmy");
        assertThat(StatementImporter.defaultDateFormat("SA")).isEqualTo("dmy");
        assertThat(StatementImporter.defaultDateFormat("US")).isEqualTo("mdy");
    }

    // ---- API

    @Test
    void lebaneseUserGetsDayFirstDates() {
        api.patch("/api/v1/auth/me/", m("country", "LB"));
        Response r = upload("Date,Description,Amount\n03/04/2026,Spinneys,-20\n");
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(200);
        assertThat(r.str("date_format")).isEqualTo("dmy");
        assertThat(txns().get(0).date).isEqualTo(LocalDate.of(2026, 4, 3));
    }

    @Test
    void explicitMonthFirst() {
        Response r = upload("Date,Description,Amount\n03/04/2026,Shop,-20\n", "date_format", "mdy");
        assertThat(r.str("date_format")).isEqualTo("mdy");
        assertThat(txns().get(0).date).isEqualTo(LocalDate.of(2026, 3, 4));
    }

    @Test
    void autoDetectsFormatFromFile() {
        api.patch("/api/v1/auth/me/", m("country", "US"));
        Response r = upload("Date,Description,Amount\n01/02/2026,A,-1\n25/02/2026,B,-1\n");
        assertThat(r.str("date_format")).isEqualTo("dmy");
        assertThat(txns().get(0).date).isEqualTo(LocalDate.of(2026, 2, 1));
    }

    @Test
    void currencyAndAccountApplied() {
        String acc = createAccount(api, "Al Rajhi");
        Response r = upload("Date,Description,Amount\n2026-04-03,Jarir,-150\n", "currency", "SAR", "account_id", acc);
        assertThat(r.str("currency")).isEqualTo("SAR");
        Transaction t = txns().get(0);
        assertThat(t.currency).isEqualTo("SAR");
        assertThat(t.incomeSourceId).isEqualTo(acc);
        assertThat(t.sourceAccount).isEqualTo("Al Rajhi");
    }

    @Test
    void repeatedRowsImportButReuploadDoesNot() {
        String csv = "Date,Description,Amount\n2026-04-03,Coffee,-3\n2026-04-03,Coffee,-3\n";
        assertThat(upload(csv).get("created")).isEqualTo(2);
        Response again = upload(csv);
        assertThat(again.get("created")).isEqualTo(0);
        assertThat(again.get("skipped")).isEqualTo(2);
        assertThat(txns()).hasSize(2);
    }

    @Test
    void nonUtf8FileIsRead() {
        byte[] content = "Date,Description,Amount\n2026-04-03,Café Beyrouth,-5\n".getBytes(StandardCharsets.ISO_8859_1);
        Response r = api.upload(URL, "statement.csv", content);
        assertThat(r.get("created")).isEqualTo(1);
        assertThat(txns().get(0).description).isEqualTo("Café Beyrouth");
    }

    @Test
    void debitCreditColumns() {
        Response r = upload("Date;Details;Debit;Credit\n2026-04-01;Salary;;5000\n2026-04-02;Rent;1200;\n");
        assertThat(r.get("created")).isEqualTo(2);
        Map<String, Transaction> byDesc = txns().stream().collect(Collectors.toMap(t -> t.description, t -> t));
        assertThat(byDesc.get("Salary").direction).isEqualTo("income");
        assertThat(byDesc.get("Salary").amount).isEqualByComparingTo("5000");
        assertThat(byDesc.get("Rent").direction).isEqualTo("expense");
        assertThat(byDesc.get("Rent").amount).isEqualByComparingTo("1200");
    }

    @Test
    void xlsxImport() throws Exception {
        byte[] bytes;
        try (XSSFWorkbook wb = new XSSFWorkbook(); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            Sheet ws = wb.createSheet();
            Row header = ws.createRow(0);
            header.createCell(0).setCellValue("Date");
            header.createCell(1).setCellValue("Description");
            header.createCell(2).setCellValue("Amount");
            Row row = ws.createRow(1);
            CellStyle dateStyle = wb.createCellStyle();
            dateStyle.setDataFormat(wb.getCreationHelper().createDataFormat().getFormat("yyyy-mm-dd"));
            row.createCell(0).setCellValue(LocalDate.of(2026, 4, 3));
            row.getCell(0).setCellStyle(dateStyle);
            row.createCell(1).setCellValue("Panda");
            row.createCell(2).setCellValue(-42.5);
            wb.write(out);
            bytes = out.toByteArray();
        }
        Response r = api.upload(URL, "statement.xlsx", bytes);
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(200);
        Transaction t = txns().get(0);
        assertThat(t.date).isEqualTo(LocalDate.of(2026, 4, 3));
        assertThat(t.amount).isEqualByComparingTo(new BigDecimal("42.5"));
    }

    @Test
    @SuppressWarnings("unchecked")
    void badRowsAreReported() {
        Response r = upload("Date,Description,Amount\nnot-a-date,Shop,-1\n2026-04-03,Ok,-2\n");
        assertThat(r.get("created")).isEqualTo(1);
        assertThat(r.get("skipped")).isEqualTo(1);
        assertThat(((List<Map<String, Object>>) r.get("errors")).get(0).get("row")).isEqualTo(2);
    }

    @Test
    void rejectsWrongTypeAndOversize() {
        assertThat(api.upload(URL, "statement.pdf", "x".getBytes(StandardCharsets.UTF_8)).status()).isEqualTo(400);
        long before = props.getImportLimits().getMaxBytes();
        props.getImportLimits().setMaxBytes(10);
        try {
            assertThat(upload("Date,Description,Amount\n2026-04-03,Shop,-1\n").status()).isEqualTo(400);
        } finally {
            props.getImportLimits().setMaxBytes(before);
        }
    }

    @Test
    void rejectsUnknownCurrencyAndFormat() {
        String csv = "Date,Description,Amount\n2026-04-03,Shop,-1\n";
        assertThat(upload(csv, "currency", "XYZ").status()).isEqualTo(400);
        assertThat(upload(csv, "date_format", "yyyy").status()).isEqualTo(400);
    }
}
