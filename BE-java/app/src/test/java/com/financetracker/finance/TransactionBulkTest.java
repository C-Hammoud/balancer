package com.financetracker.finance;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.LocalDate;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import com.financetracker.ApiTestSupport;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.finance.domain.FinanceRepositories.TransactionRepository;

/** Port of BE/tests/test_transaction_bulk.py: months list, deleting months, bulk delete/update. */
class TransactionBulkTest extends ApiTestSupport {

    @Autowired
    TransactionRepository transactions;

    UserAccount user;
    Api api;

    @BeforeEach
    void setUp() {
        user = makeUser();
        api = api(user);
    }

    private Set<String> ids(UserAccount u) {
        return transactions.findByUserIdOrderByIdAsc(u.userId()).stream().map(t -> t.id).collect(Collectors.toSet());
    }

    private Map<String, Object> income(String account, Object amount, LocalDate d) {
        Response r = api.post(B + "/transactions/", m("date", d.toString(), "direction", "income", "description", "Salary",
                "amount", String.valueOf(amount), "account_id", account));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(201);
        return r.map();
    }

    @Test
    void monthsListCountsAndTotals() {
        String cat = createCategory(api)[1];
        String bank = createAccount(api);
        addExpense(api, bank, cat, 30, LocalDate.of(2026, 9, 3));
        addExpense(api, bank, cat, 20, LocalDate.of(2026, 9, 20));
        income(bank, 1000, LocalDate.of(2026, 9, 1));
        addExpense(api, bank, cat, 5, LocalDate.of(2026, 10, 2));
        Api other = api(makeUser());
        addExpense(other, createAccount(other), createCategory(other)[1], 99, LocalDate.of(2026, 8, 1));

        Response r = api.get(B + "/transactions/months/");
        assertThat(r.status()).isEqualTo(200);
        List<Map<String, Object>> rows = r.list();
        assertThat(rows).extracting(row -> row.get("month")).containsExactly("2026-10", "2026-09");
        Map<String, Object> sep = rows.get(1);
        assertThat(List.of(sep.get("count"), sep.get("income_count"), sep.get("expense_count"))).containsExactly(3, 1, 2);
        assertThat(sep.get("first_date")).isEqualTo("2026-09-01");
        assertThat(sep.get("last_date")).isEqualTo("2026-09-20");
        assertThat(sep.get("totals")).isEqualTo(List.of(Map.of("currency", "USD", "income", "1000.00", "expense", "50.00")));
    }

    @Test
    void deleteMonthsRemovesOnlyThoseMonths() {
        String cat = createCategory(api)[1];
        String bank = createAccount(api);
        addExpense(api, bank, cat, 30, LocalDate.of(2026, 8, 3));
        addExpense(api, bank, cat, 20, LocalDate.of(2026, 9, 3));
        Map<String, Object> keep = addExpense(api, bank, cat, 10, LocalDate.of(2026, 10, 3));
        UserAccount otherUser = makeUser();
        Api other = api(otherUser);
        addExpense(other, createAccount(other), createCategory(other)[1], 99, LocalDate.of(2026, 8, 1));

        Response r = api.post(B + "/transactions/months/delete/", m("months", List.of("2026-08", "2026-09")));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(200);
        assertThat(r.get("deleted")).isEqualTo(2);
        assertThat(r.get("months")).isEqualTo(List.of("2026-08", "2026-09"));
        assertThat(ids(user)).containsExactly((String) keep.get("id"));
        assertThat(ids(otherUser)).hasSize(1);

        for (Object bad : List.of(List.of(), List.of("2026-13"), List.of("Sept"))) {
            assertThat(api.post(B + "/transactions/months/delete/", m("months", bad)).status()).isEqualTo(400);
        }
    }

    @Test
    void bulkDeleteSelectedIgnoresForeignIdsAndReopensInstallments() {
        String cat = createCategory(api)[1];
        String bank = createAccount(api);
        Map<String, Object> a = addExpense(api, bank, cat, 1);
        Map<String, Object> b = addExpense(api, bank, cat, 2);
        Map<String, Object> c = addExpense(api, bank, cat, 3);
        Api other = api(makeUser());
        Map<String, Object> foreign = addExpense(other, createAccount(other), createCategory(other)[1], 9);

        Response r = api.post(B + "/transactions/bulk/", m("ids", List.of(a.get("id"), b.get("id"), foreign.get("id")),
                "action", "delete"));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(200);
        assertThat(r.map()).isEqualTo(Map.of("deleted", 2, "missing", 1));
        assertThat(ids(user)).containsExactly((String) c.get("id"));
        assertThat(api.post(B + "/transactions/bulk/", m("ids", List.of(foreign.get("id")), "action", "delete")).status())
                .isEqualTo(404);

        Response loan = api.post(B + "/commitments/", m("name", "Car loan", "amount", "300", "start_date", "2026-10-05",
                "term_months", 3, "frequency", "monthly", "payment_amount", "100", "currency", "USD"));
        String cid = loan.str("id");
        @SuppressWarnings("unchecked")
        String lineId = (String) ((List<Map<String, Object>>) api.get(B + "/commitments/" + cid + "/").get("schedule"))
                .get(0).get("id");
        String txn = api.post(B + "/commitments/" + cid + "/schedule/" + lineId + "/pay/", m("paid_date", "2026-10-05"))
                .str("transaction_id");
        assertThat(api.post(B + "/transactions/bulk/", m("ids", List.of(txn), "action", "delete")).status()).isEqualTo(200);
        @SuppressWarnings("unchecked")
        Object status = ((List<Map<String, Object>>) api.get(B + "/commitments/" + cid + "/").get("schedule")).get(0)
                .get("status");
        assertThat(status).isEqualTo("outstanding");
    }

    @Test
    void bulkUpdateAccountAndMerchant() {
        String groceries = createCategory(api, "Food", "Groceries")[1];
        String bank = createAccount(api, "Bank");
        String card = createAccount(api, "Card");
        Response e1r = api.post(B + "/transactions/", m("date", LocalDate.now().toString(), "description", "CARREFOUR 123",
                "amount", "12", "direction", "expense", "category_id", null, "account_id", bank));
        assertThat(e1r.status()).as(String.valueOf(e1r.body())).isEqualTo(201);
        String e1 = e1r.str("id");
        String inc = (String) income(bank, 500, LocalDate.now()).get("id");

        Response r = api.post(B + "/transactions/bulk/", m("ids", List.of(e1, inc), "action", "update",
                "changes", m("account_id", card, "category_id", groceries)));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(200);
        assertThat(r.map()).isEqualTo(Map.of("updated", 2, "skipped", 0, "missing", 0));
        Response t1 = api.get(B + "/transactions/" + e1 + "/");
        assertThat(t1.get("category_id")).isEqualTo(groceries);
        assertThat(t1.get("description")).isEqualTo("Groceries");
        assertThat(t1.get("note")).isEqualTo("CARREFOUR 123");
        assertThat(t1.get("income_source_id")).isEqualTo(card);
        Response t2 = api.get(B + "/transactions/" + inc + "/");
        assertThat(t2.get("category_id")).isNull();
        assertThat(t2.get("income_source_id")).isEqualTo(card);

        // Already matching: skipped. Unknown fields and a foreign account: 400.
        r = api.post(B + "/transactions/bulk/", m("ids", List.of(e1, inc), "action", "update", "changes", m("account_id", card)));
        assertThat(r.map()).isEqualTo(Map.of("updated", 0, "skipped", 2, "missing", 0));
        assertThat(api.post(B + "/transactions/bulk/", m("ids", List.of(e1), "action", "update",
                "changes", m("amount", "1"))).status()).isEqualTo(400);
        Api other = api(makeUser());
        assertThat(api.post(B + "/transactions/bulk/", m("ids", List.of(e1), "action", "update",
                "changes", m("account_id", createAccount(other)))).status()).isEqualTo(400);
        assertThat(api.post(B + "/transactions/bulk/", m("ids", List.of(), "action", "delete")).status()).isEqualTo(400);
    }
}
