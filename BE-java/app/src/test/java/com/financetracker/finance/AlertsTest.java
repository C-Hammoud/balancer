package com.financetracker.finance;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import java.time.Instant;
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
import com.financetracker.finance.application.AlertService;
import com.financetracker.finance.domain.BudgetAlert;
import com.financetracker.finance.domain.FinanceRepositories.BudgetAlertRepository;

/** Port of BE/tests/test_alerts.py. */
class AlertsTest extends ApiTestSupport {

    @Autowired
    AlertService alerts;
    @Autowired
    BudgetAlertRepository alertRepository;

    UserAccount user;
    Api api;
    String category;
    String account;

    /** over_budget: Groceries budget 100, spent 95 -> WARN alerts for Groceries and its group Food. */
    @BeforeEach
    void overBudget() {
        user = makeUser();
        api = api(user);
        category = createCategory(api)[1];
        account = createAccount(api);
        setBudget(api, category, 100);
        addExpense(api, account, category, 95);
        alerts.refresh(user.userId(), null, null, true);
    }

    private List<Map<String, Object>> list(Api client, String show) {
        Response r = client.get(B + "/alerts/", "show", show);
        assertThat(r.status()).isEqualTo(200);
        return r.list();
    }

    private List<String> ids(String categoryId, String show) {
        return list(api, show).stream().filter(a -> categoryId.equals(a.get("category_id")))
                .map(a -> (String) a.get("id")).toList();
    }

    private String alertId() {
        List<String> ids = ids(category, "open");
        assertThat(ids).hasSize(1);
        return ids.get(0);
    }

    @Test
    void warnAlertsForSubcategoryAndGroup() {
        List<Map<String, Object>> open = list(api, "open");
        assertThat(open).hasSize(2);
        List<String> cats = open.stream().map(a -> (String) a.get("category_id")).toList();
        assertThat(cats).contains(category);
        assertThat(cats).anyMatch(c -> c.startsWith("group:"));
        assertThat(open.stream().map(a -> a.get("severity")).collect(Collectors.toSet())).isEqualTo(Set.of("WARN"));
        assertThat(open.stream().map(a -> a.get("state")).collect(Collectors.toSet())).isEqualTo(Set.of("open"));
    }

    @Test
    void userResolveSurvivesReevaluation() {
        String id = alertId();
        assertThat(api.post(B + "/alerts/" + id + "/resolve/").status()).isEqualTo(200);
        alerts.refresh(user.userId(), null, null, true); // condition still holds (95%)
        assertThat(ids(category, "open")).isEmpty();
        assertThat(list(api, "resolved")).anyMatch(a -> id.equals(a.get("id")) && "user".equals(a.get("resolution")));
    }

    @Test
    void autoResolvedAlertReopensWhenConditionReturns() {
        String id = alertId();
        setBudget(api, category, 1000);
        alerts.refresh(user.userId(), null, null, true);
        assertThat(list(api, "resolved")).anyMatch(a -> id.equals(a.get("id")) && "auto".equals(a.get("resolution")));
        setBudget(api, category, 100);
        alerts.refresh(user.userId(), null, null, true);
        assertThat(ids(category, "open")).containsExactly(id);
    }

    @Test
    void snoozeHidesFromOpenAndBadge() {
        int before = (int) api.get(B + "/alerts/count/").get("count");
        String id = alertId();
        Response r = api.post(B + "/alerts/" + id + "/snooze/", m("days", 3));
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.str("state")).isEqualTo("snoozed");
        assertThat(r.str("snoozed_until")).isNotBlank();
        assertThat(ids(category, "open")).isEmpty();
        assertThat(ids(category, "snoozed")).containsExactly(id);
        Response counts = api.get(B + "/alerts/count/");
        assertThat(counts.get("count")).isEqualTo(before - 1);
        assertThat(counts.get("snoozed")).isEqualTo(1);
        assertThat(api.delete(B + "/alerts/" + id + "/snooze/").status()).isEqualTo(200);
        assertThat(ids(category, "open")).containsExactly(id);
    }

    @Test
    void snoozeRejectsUnknownDuration() {
        assertThat(api.post(B + "/alerts/" + alertId() + "/snooze/", m("days", 30)).status()).isEqualTo(400);
    }

    @Test
    void expiredSnoozeReturnsToOpen() {
        String id = alertId();
        BudgetAlert a = alertRepository.findById(id).orElseThrow();
        a.snoozedUntil = Instant.now().minusSeconds(60);
        alertRepository.save(a);
        assertThat(ids(category, "open")).containsExactly(id);
    }

    @Test
    void snoozedAlertIsNotEmailed() {
        for (Map<String, Object> row : list(api, "open")) {
            BudgetAlert a = alertRepository.findById((String) row.get("id")).orElseThrow();
            a.emailSent = false;
            alertRepository.save(a);
            api.post(B + "/alerts/" + row.get("id") + "/snooze/", m("days", 1));
        }
        clearInvocations(emailDelivery);
        assertThat(alerts.sendPendingEmails(user.userId())).isZero();
        alerts.refresh(user.userId(), null, null, true);
        verify(emailDelivery, never()).sendNotification(any(), any());
    }

    @Test
    void reopen() {
        String id = alertId();
        api.post(B + "/alerts/" + id + "/resolve/");
        Response r = api.post(B + "/alerts/" + id + "/reopen/");
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.str("state")).isEqualTo("open");
        assertThat(ids(category, "open")).containsExactly(id);
    }

    @Test
    void bulkActionsOnlyTouchOwnAlerts() {
        UserAccount other = makeUser();
        Api otherApi = api(other);
        String cat = createCategory(otherApi, "Home", "Rent")[1];
        String acc = createAccount(otherApi);
        setBudget(otherApi, cat, 10);
        addExpense(otherApi, acc, cat, 50);
        alerts.refresh(other.userId(), null, null, true);
        List<String> otherIds = list(otherApi, "open").stream().map(a -> (String) a.get("id")).toList();
        assertThat(otherIds).isNotEmpty();

        List<String> mine = list(api, "open").stream().map(a -> (String) a.get("id")).toList();
        List<String> all = new java.util.ArrayList<>(mine);
        all.addAll(otherIds);
        Response r = api.post(B + "/alerts/bulk/", m("action", "resolve", "ids", all));
        assertThat(r.status()).isEqualTo(200);
        @SuppressWarnings("unchecked")
        List<Object> updated = (List<Object>) r.get("updated");
        @SuppressWarnings("unchecked")
        List<Object> failed = (List<Object>) r.get("failed");
        assertThat(updated).containsExactlyInAnyOrderElementsOf(mine);
        assertThat(failed).containsExactlyInAnyOrderElementsOf(otherIds);
        assertThat(list(otherApi, "open").stream().map(a -> a.get("id")).toList()).containsExactlyInAnyOrderElementsOf(otherIds);
    }

    @Test
    void bulkValidation() {
        assertThat(api.post(B + "/alerts/bulk/", m("action", "resolve", "ids", List.of())).status()).isEqualTo(400);
        assertThat(api.post(B + "/alerts/bulk/", m("action", "explode", "ids", List.of("1"))).status()).isEqualTo(400);
        assertThat(api.post(B + "/alerts/bulk/", m("action", "snooze", "ids", List.of("1"), "days", 2)).status()).isEqualTo(400);
    }

    private String[] commitmentDueAlert() {
        LocalDate due = LocalDate.now().plusDays(1);
        Response r = api.post(B + "/commitments/", m("name", "Car loan", "amount", "1200", "start_date", due.toString(),
                "term_months", 12, "frequency", "monthly", "payment_amount", "100", "currency", "USD",
                "reminder_days_before", 3));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(201);
        alerts.refresh(user.userId(), null, null, true);
        List<Map<String, Object>> due1 = list(api, "open").stream()
                .filter(a -> "commitment_due".equals(a.get("alert_type"))).toList();
        assertThat(due1).hasSize(1);
        return new String[] {r.str("id"), (String) due1.get(0).get("id")};
    }

    @Test
    void payFromAlertRecordsTransactionWithAccount() {
        String cat = createCategory(api, "Loans", "Car")[1];
        String[] ids = commitmentDueAlert();
        Response r = api.post(B + "/alerts/" + ids[1] + "/record-commitment/",
                m("category_id", cat, "account_id", account, "payment_date", LocalDate.now().toString()));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(201);
        @SuppressWarnings("unchecked")
        Map<String, Object> txn = (Map<String, Object>) r.get("transaction");
        assertThat(txn.get("account_id")).isEqualTo(account);
        assertThat(txn.get("amount")).isEqualTo("100.00");
        assertThat(txn.get("commitment_id")).isEqualTo(ids[0]);
        assertThat(api.get(B + "/commitments/" + ids[0] + "/").get("payments_completed")).isEqualTo(1);
        assertThat(list(api, "open")).noneMatch(a -> ids[1].equals(a.get("id")));
    }

    @Test
    void payFromAlertRejectsOtherUsersAccount() {
        String cat = createCategory(api, "Loans", "Car")[1];
        String otherAcc = createAccount(api(makeUser()), "Not mine");
        String[] ids = commitmentDueAlert();
        Response r = api.post(B + "/alerts/" + ids[1] + "/record-commitment/", m("category_id", cat, "account_id", otherAcc));
        assertThat(r.status()).isEqualTo(400);
    }
}
