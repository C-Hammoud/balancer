package com.financetracker.finance;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import com.financetracker.ApiTestSupport;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.finance.application.ReportService;
import com.financetracker.finance.domain.FinanceRepositories.TransactionRepository;
import com.financetracker.finance.domain.Transaction;
import com.financetracker.shared.locale.ExchangeRates;

/** Port of BE/tests/test_money.py: loan pay/unpay, regenerate keeps history, savings currency. */
class MoneyTest extends ApiTestSupport {

    @Autowired
    ReportService reports;
    @Autowired
    TransactionRepository transactions;
    @Autowired
    ExchangeRates rates;

    UserAccount user;
    Api api;

    @BeforeEach
    void setUp() {
        user = makeUser();
        api = api(user);
    }

    @SuppressWarnings("unchecked")
    private Object[] loan(LocalDate start, int term) {
        Response r = api.post(B + "/commitments/", m("name", "Car loan", "amount", "300", "start_date", start.toString(),
                "term_months", term, "frequency", "monthly", "payment_amount", "100", "currency", "USD"));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(201);
        String cid = r.str("id");
        List<Map<String, Object>> schedule = (List<Map<String, Object>>) api.get(B + "/commitments/" + cid + "/").get("schedule");
        return new Object[] {cid, schedule};
    }

    @SuppressWarnings("unchecked")
    private List<Map<String, Object>> schedule(Object[] loan) {
        return (List<Map<String, Object>>) loan[1];
    }

    private List<Transaction> expenses(String month) {
        return transactions.listByUser(user.userId(), month, 500).stream().filter(t -> "expense".equals(t.direction)).toList();
    }

    private String payUrl(Object[] loan, int idx) {
        return B + "/commitments/" + loan[0] + "/schedule/" + schedule(loan).get(idx).get("id") + "/pay/";
    }

    @Test
    void markingPaidRecordsExpenseSoSavingsDoNotRise() {
        Object[] loan = loan(LocalDate.of(2026, 10, 5), 3);
        BigDecimal before = reports.savingsActual(user.userId(), 2026, 10, null);
        assertThat(before).isEqualByComparingTo("-100");
        Response r = api.post(payUrl(loan, 0), m("paid_date", "2026-10-05"));
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.str("transaction_id")).isNotBlank();
        assertThat(expenses("2026-10")).hasSize(1);
        assertThat(reports.savingsActual(user.userId(), 2026, 10, null)).isEqualByComparingTo(before);
    }

    @Test
    void payIsIdempotent() {
        Object[] loan = loan(LocalDate.of(2026, 10, 5), 3);
        api.post(payUrl(loan, 0), m("paid_date", "2026-10-05"));
        api.post(payUrl(loan, 0), m("paid_date", "2026-10-05"));
        assertThat(expenses("2026-10")).hasSize(1);
    }

    @Test
    void unpayRemovesTheExpense() {
        Object[] loan = loan(LocalDate.of(2026, 10, 5), 3);
        String lineId = (String) schedule(loan).get(0).get("id");
        api.post(payUrl(loan, 0), m("paid_date", "2026-10-05"));
        Response r = api.post(B + "/commitments/" + loan[0] + "/schedule/" + lineId + "/unpay/");
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.str("status")).isEqualTo("outstanding");
        assertThat(expenses("2026-10")).isEmpty();
    }

    @Test
    @SuppressWarnings("unchecked")
    void deletingPaymentTransactionReopensInstallment() {
        Object[] loan = loan(LocalDate.of(2026, 10, 5), 3);
        String txnId = api.post(payUrl(loan, 0), m("paid_date", "2026-10-05")).str("transaction_id");
        assertThat(api.delete(B + "/transactions/" + txnId + "/").status()).isEqualTo(204);
        List<Map<String, Object>> lines = (List<Map<String, Object>>) api.get(B + "/commitments/" + loan[0] + "/").get("schedule");
        assertThat(lines.get(0).get("status")).isEqualTo("outstanding");
    }

    @Test
    void linePatchToPaidRecordsExpense() {
        Object[] loan = loan(LocalDate.of(2026, 10, 5), 3);
        Response r = api.patch(B + "/commitments/" + loan[0] + "/schedule/" + schedule(loan).get(0).get("id") + "/",
                m("payment_date", "2026-10-07", "status", "paid"));
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.str("status")).isEqualTo("paid");
        List<Transaction> exp = expenses("2026-10");
        assertThat(exp).hasSize(1);
        assertThat(exp.get(0).date).isEqualTo(LocalDate.of(2026, 10, 7));
    }

    @Test
    @SuppressWarnings("unchecked")
    void regenerateKeepsPaidHistory() {
        Object[] loan = loan(LocalDate.of(2026, 10, 5), 3);
        String paidId = (String) schedule(loan).get(0).get("id");
        api.post(payUrl(loan, 0), m("paid_date", "2026-10-05"));
        Response r = api.post(B + "/commitments/" + loan[0] + "/regenerate-schedule/");
        assertThat(r.status()).isEqualTo(200);
        List<Map<String, Object>> lines = (List<Map<String, Object>>) r.get("schedule");
        assertThat(lines).hasSize(3);
        assertThat(lines.stream().filter(l -> "paid".equals(l.get("status"))).map(l -> l.get("id")).toList()).containsExactly(paidId);
        assertThat(expenses("2026-10").get(0).scheduleLineId).isEqualTo(paidId);
    }

    @Test
    void changingTermsKeepsPaidLines() {
        Object[] loan = loan(LocalDate.of(2026, 10, 5), 3);
        api.post(payUrl(loan, 0), m("paid_date", "2026-10-05"));
        api.patch(B + "/commitments/" + loan[0] + "/", m("term_months", 6));
        Response detail = api.get(B + "/commitments/" + loan[0] + "/");
        assertThat(detail.get("payments_total")).isEqualTo(6);
        assertThat(detail.get("payments_completed")).isEqualTo(1);
    }

    @Test
    void savingsConvertCurrencies() {
        String acc = createAccount(api);
        api.patch("/api/v1/auth/me/", m("default_currency", "USD"));
        api.post(B + "/transactions/", m("date", "2026-10-01", "description", "Salary", "amount", "3750", "currency", "SAR",
                "direction", "income", "account_id", acc));
        api.post(B + "/transactions/", m("date", "2026-10-02", "description", "Rent", "amount", "500", "currency", "USD",
                "direction", "expense", "account_id", acc));
        // 3750 SAR = 1000 USD; mixing units would give 3250
        assertThat(reports.savingsActual(user.userId(), 2026, 10, "USD")).isEqualByComparingTo("500.00");
        assertThat(api.get(B + "/savings/2026/10/").status()).isIn(200, 404);
    }

    @Test
    void lbpRateIsCurrent() {
        assertThat(rates.convert(new BigDecimal("89500"), "LBP", "USD")).isEqualTo(new BigDecimal("1.00"));
        assertThat(rates.convert(new BigDecimal("3.75"), "SAR", "USD")).isEqualTo(new BigDecimal("1.00"));
    }
}
