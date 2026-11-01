package com.financetracker.finance;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.clearInvocations;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;

import com.financetracker.ApiTestSupport;
import com.financetracker.access.application.ProfileService;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.finance.application.PlanTriggerService;
import com.financetracker.finance.application.PlanningService;
import com.financetracker.finance.domain.BudgetPlan;
import com.financetracker.finance.domain.FinanceRepositories.BudgetPlanRepository;
import com.financetracker.finance.domain.FinanceRepositories.IncomeStreamRepository;
import com.financetracker.finance.domain.IncomeStream;
import com.financetracker.notifications.email.BrandedEmail;
import com.financetracker.notifications.inbox.AppNotification;
import com.financetracker.notifications.inbox.AppNotificationRepository;

/** Port of BE/tests/test_plan_triggers.py. */
class PlanTriggersTest extends ApiTestSupport {

    static final LocalDate NOV = LocalDate.of(2026, 11, 3);

    @Autowired
    PlanTriggerService triggers;
    @Autowired
    PlanningService planning;
    @Autowired
    BudgetPlanRepository plans;
    @Autowired
    IncomeStreamRepository streams;
    @Autowired
    AppNotificationRepository notifications;
    @Autowired
    ProfileService profileService;

    UserAccount user;
    Api api;
    String movies;
    String acc;

    @BeforeEach
    void setUp() {
        user = makeUser();
        api = api(user);
        createCategory(api, "Home", "Rent");
        movies = createCategory(api, "Fun", "Movies")[1];
        acc = createAccount(api);
    }

    private void income() {
        IncomeStream s = new IncomeStream();
        s.userId = user.userId();
        s.name = "Salary";
        s.amount = new BigDecimal("4000");
        s.currency = "USD";
        streams.save(s);
    }

    private List<AppNotification> notes(String kind) {
        return notifications.listByUser(user.userId(), 2000).stream().filter(n -> kind == null || kind.equals(n.kind)).toList();
    }

    @Test
    void monthlySuggestionNotifiesOnce() {
        income();
        clearInvocations(emailDelivery);
        assertThat(triggers.checkMonthly(user.userId(), NOV)).isTrue();
        assertThat(triggers.checkMonthly(user.userId(), NOV)).isFalse(); // pending suggestion exists
        List<BudgetPlan> forMonth = plans.listForMonth(user.userId(), 2026, 11);
        assertThat(forMonth).hasSize(1);
        assertThat(forMonth.get(0).reason).isEqualTo("monthly");
        List<AppNotification> n = notes("plan_suggested");
        assertThat(n).hasSize(1);
        assertThat(n.get(0).link).isEqualTo("/budgeting/plan?id=" + forMonth.get(0).id);
        ArgumentCaptor<BrandedEmail> sent = ArgumentCaptor.forClass(BrandedEmail.class);
        verify(emailDelivery, times(1)).sendNotification(sent.capture(), any());
        assertThat(sent.getValue().subject().toLowerCase()).contains("budget plan");
    }

    @Test
    void dismissedMonthIsNotRenotified() {
        income();
        triggers.checkMonthly(user.userId(), NOV);
        BudgetPlan p = plans.listForMonth(user.userId(), 2026, 11).get(0);
        p.status = "dismissed";
        plans.save(p);
        assertThat(triggers.checkMonthly(user.userId(), NOV)).isFalse(); // same fingerprint
        assertThat(notes(null)).hasSize(1);
    }

    @Test
    void optOutSendsNothing() {
        income();
        profileService.applySetupPatch(user, Map.of("notify_plan_updates", false));
        clearInvocations(emailDelivery);
        assertThat(triggers.checkMonthly(user.userId(), NOV)).isFalse();
        assertThat(notes(null)).isEmpty();
        verify(emailDelivery, never()).sendNotification(any(), any());
    }

    @Test
    void missingIncomeAsksForIncome() {
        assertThat(triggers.checkMonthly(user.userId(), NOV)).isTrue();
        assertThat(notes(null).stream().map(n -> n.kind).toList()).containsExactly("plan_needs_income");
        assertThat(plans.listForMonth(user.userId(), 2026, 11)).isEmpty();
    }

    @Test
    void incomeDriftOver10Percent() {
        income();
        api.post(B + "/transactions/", m("date", "2026-10-25", "description", "Salary", "amount", "5000",
                "direction", "income", "account_id", acc));
        assertThat(triggers.checkIncomeChange(user.userId(), NOV)).isTrue();
        AppNotification n = notes("plan_suggested").get(0);
        assertThat(n.body).contains("5,000").contains("more than");
    }

    @Test
    void incomeWithin10PercentIsQuiet() {
        income();
        api.post(B + "/transactions/", m("date", "2026-10-25", "description", "Salary", "amount", "4200",
                "direction", "income", "account_id", acc));
        assertThat(triggers.checkIncomeChange(user.userId(), NOV)).isFalse();
    }

    @Test
    void commitmentChangeSuggestsPlan() {
        income();
        Response r = api.post(B + "/commitments/", m("name", "Car loan", "amount", "12000",
                "start_date", LocalDate.now().toString(), "term_months", 12, "frequency", "monthly",
                "payment_amount", "1000", "currency", "USD"));
        assertThat(r.status()).isEqualTo(201);
        List<AppNotification> n = notes("plan_suggested");
        assertThat(n).hasSize(1);
        assertThat(n.get(0).body).contains("Car loan");
        Map<String, Object> plan = planning.planToMap(plans.findById(n.get(0).relatedId).orElseThrow());
        assertThat(plan.get("reason")).isEqualTo("commitment_change");
        assertDec(plan.get("commitments_total"), "1000");
    }

    @Test
    void overspendingMidMonth() {
        income();
        BudgetPlan obj = planning.savePlan(user.userId(),
                planning.buildPlan(user.userId(), 2026, 11, "rule_50_30_20", "USD", 20), "manual");
        planning.accept(user.userId(), obj); // plans 800 savings
        addExpense(api, acc, movies, 3000, LocalDate.of(2026, 11, 10));
        assertThat(triggers.checkOverspending(user.userId(), LocalDate.of(2026, 11, 10))).isFalse(); // before day 15
        assertThat(triggers.checkOverspending(user.userId(), LocalDate.of(2026, 11, 16))).isTrue();
        assertThat(triggers.checkOverspending(user.userId(), LocalDate.of(2026, 11, 17))).isFalse(); // once per month
    }

    @Test
    void reviewAllCountsUsers() {
        income();
        Map<String, Integer> totals = triggers.reviewAll();
        assertThat(totals.get("users")).isGreaterThanOrEqualTo(1);
        assertThat(totals).containsKeys("monthly", "income_change", "overspending", "errors");
    }
}
