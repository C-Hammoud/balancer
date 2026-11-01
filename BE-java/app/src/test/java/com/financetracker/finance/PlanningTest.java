package com.financetracker.finance;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import com.financetracker.ApiTestSupport;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.finance.application.PlanningService;
import com.financetracker.finance.domain.BudgetPlan;
import com.financetracker.finance.domain.FinanceRepositories.BudgetPlanRepository;
import com.financetracker.finance.domain.FinanceRepositories.BudgetRepository;
import com.financetracker.finance.domain.FinanceRepositories.IncomeStreamRepository;
import com.financetracker.finance.domain.FinanceRepositories.SavingsRepository;
import com.financetracker.finance.domain.IncomeStream;

/** Port of BE/tests/test_planning.py: 50/30/20 (+ debt-aware), spending-based, currency, rounding, accept. */
class PlanningTest extends ApiTestSupport {

    static final int Y = 2026;
    static final int M = 11;

    @Autowired
    PlanningService planning;
    @Autowired
    IncomeStreamRepository streams;
    @Autowired
    BudgetRepository budgets;
    @Autowired
    BudgetPlanRepository plans;
    @Autowired
    SavingsRepository savings;

    UserAccount user;
    Api api;
    String home;
    String fun;
    String rent;
    String movies;
    String acc;

    @BeforeEach
    void setUp() {
        user = makeUser();
        api = api(user);
        String[] h = createCategory(api, "Home", "Rent");
        String[] f = createCategory(api, "Fun", "Movies");
        home = h[0];
        rent = h[1];
        fun = f[0];
        movies = f[1];
        acc = createAccount(api);
        stream("Salary", "5000", "USD", "monthly");
    }

    private void stream(String name, String amount, String currency, String frequency) {
        IncomeStream s = new IncomeStream();
        s.userId = user.userId();
        s.name = name;
        s.amount = new BigDecimal(amount);
        s.currency = currency;
        s.frequency = frequency;
        streams.save(s);
    }

    private void loan(int payment) {
        Response r = api.post(B + "/commitments/", m("name", "Loan", "amount", String.valueOf(payment * 12),
                "start_date", "2026-11-10", "term_months", 12, "frequency", "monthly",
                "payment_amount", String.valueOf(payment), "currency", "USD"));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(201);
    }

    private void history(int homeAmount, int funAmount) {
        for (int mo : new int[] {8, 9, 10}) {
            addExpense(api, acc, rent, homeAmount, LocalDate.of(2026, mo, 5));
            addExpense(api, acc, movies, funAmount, LocalDate.of(2026, mo, 6));
        }
    }

    @SuppressWarnings("unchecked")
    private static Map<String, BigDecimal> lines(Map<String, Object> plan) {
        Map<String, BigDecimal> out = new LinkedHashMap<>();
        for (Map<String, Object> l : (List<Map<String, Object>>) plan.get("lines")) {
            out.put((String) l.get("group_name"), (BigDecimal) l.get("amount"));
        }
        return out;
    }

    private Map<String, Object> build(String kind, int pct, String currency) {
        return planning.buildPlan(user.userId(), Y, M, kind, currency, pct);
    }

    private Map<String, Object> build() {
        return build("rule_50_30_20", 20, "USD");
    }

    @SuppressWarnings("unchecked")
    private static List<String> warnings(Map<String, Object> plan) {
        return (List<String>) plan.get("warnings");
    }

    private static void assertLines(Map<String, Object> plan, String homeAmount, String funAmount) {
        Map<String, BigDecimal> l = lines(plan);
        assertThat(l.get("Home")).isEqualByComparingTo(homeAmount);
        assertThat(l.get("Fun")).isEqualByComparingTo(funAmount);
    }

    @Test
    void rule503020Basic() {
        Map<String, Object> p = build();
        assertLines(p, "2500", "1500");
        assertDec(p.get("savings_amount"), "1000");
        assertThat(p.get("savings_pct")).isEqualTo(20);
        assertThat(warnings(p)).isEmpty();
    }

    @Test
    void commitmentsComeOutOfNeeds() {
        loan(1500);
        Map<String, Object> p = build();
        assertDec(p.get("commitments_total"), "1500");
        assertLines(p, "1000", "1500");
        assertDec(p.get("savings_amount"), "1000");
    }

    @Test
    void debtAwareShift() {
        loan(2000);
        Map<String, Object> p = build();
        assertLines(p, "1000", "1250");
        assertDec(p.get("savings_amount"), "750");
        assertThat(warnings(p)).anyMatch(w -> w.contains("60/25/15"));
    }

    @Test
    void heavyCommitmentsKeepEssentialsAnd5PctSavings() {
        loan(3000);
        Map<String, Object> p = build();
        assertThat(lines(p).get("Home")).isEqualByComparingTo("750");
        assertDec(p.get("savings_amount"), "250");
        assertThat(warnings(p)).hasSize(2);
    }

    @Test
    void spendingBasedSurplusGoesToSavings() {
        history(1800, 1000);
        Map<String, Object> p = build("spending_based", 20, "USD");
        assertThat(p.get("history_months")).isEqualTo(3);
        assertLines(p, "1800", "1000");
        assertDec(p.get("savings_amount"), "2200");
    }

    @Test
    void spendingBasedTrimsWantsToHitTarget() {
        history(1800, 1000);
        loan(1500);
        Map<String, Object> p = build("spending_based", 20, "USD");
        assertLines(p, "1800", "700");
        assertDec(p.get("savings_amount"), "1000");
    }

    @Test
    void spendingBasedWarnsWhenTargetUnreachable() {
        history(1800, 1000);
        loan(2500);
        Map<String, Object> p = build("spending_based", 20, "USD");
        assertThat(lines(p).get("Fun")).isEqualByComparingTo("700");
        assertThat(warnings(p)).anyMatch(w -> w.contains("less than your 20%"));
    }

    @Test
    void spendingBasedWithoutHistoryFallsBack() {
        Map<String, Object> p = build("spending_based", 20, "USD");
        assertThat(p.get("effective_type")).isEqualTo("rule_50_30_20");
        assertThat(warnings(p)).anyMatch(w -> w.contains("No spending history"));
    }

    @Test
    void incomeConvertedToPlanCurrency() {
        streams.listByUser(user.userId()).forEach(streams::delete);
        stream("Salary", "3750", "SAR", "monthly");
        stream("Side", "1200", "USD", "yearly");
        assertDec(build().get("income_total"), "1100"); // 1000 + 100
    }

    @Test
    @SuppressWarnings("unchecked")
    void lbpAmountsRoundToThousands() {
        Map<String, Object> p = build("rule_50_30_20", 20, "LBP");
        for (Map<String, Object> l : (List<Map<String, Object>>) p.get("lines")) {
            assertThat(((BigDecimal) l.get("amount")).remainder(new BigDecimal("1000"))).isEqualByComparingTo("0");
        }
    }

    @Test
    @SuppressWarnings("unchecked")
    void noIncomeGivesZeroPlan() {
        streams.listByUser(user.userId()).forEach(streams::delete);
        Map<String, Object> p = build();
        for (Map<String, Object> l : (List<Map<String, Object>>) p.get("lines")) {
            assertThat((BigDecimal) l.get("amount")).isEqualByComparingTo("0");
        }
        assertThat(warnings(p)).anyMatch(w -> w.contains("Add your expected income"));
    }

    @Test
    void acceptWritesBudgetsAndSavingsAndSupersedes() {
        BudgetPlan first = planning.savePlan(user.userId(), build(), "manual");
        BudgetPlan second = planning.savePlan(user.userId(), build("spending_based", 20, "USD"), "manual");
        assertThat(plans.findById(first.id).orElseThrow().status).isEqualTo("superseded");
        planning.accept(user.userId(), second);
        assertThat(budgets.getByUserGroupMonth(user.userId(), home, Y, M).orElseThrow().forecast).isEqualByComparingTo("2500");
        assertThat(savings.getByUserMonth(user.userId(), Y, M).orElseThrow().target).isEqualByComparingTo("1000");
        assertThat(plans.findById(second.id).orElseThrow().status).isEqualTo("accepted");
    }

    @Test
    void editingLinesRecomputesSavings() {
        BudgetPlan obj = planning.savePlan(user.userId(), build(), "manual");
        planning.updateLines(obj, m(fun, "1000"));
        Map<String, Object> plan = planning.planToMap(plans.findById(obj.id).orElseThrow());
        assertDec(plan.get("savings_amount"), "1500");
        assertThatThrownBy(() -> planning.updateLines(obj, m(fun, "-5"))).isInstanceOf(PlanningService.PlanError.class);
    }
}
