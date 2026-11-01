package com.financetracker.finance.application;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.time.format.TextStyle;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.financetracker.access.api.ProfileSettings;
import com.financetracker.access.api.UserDirectory;
import com.financetracker.access.api.UserSummary;
import com.financetracker.finance.domain.BudgetPlan;
import com.financetracker.finance.domain.FinanceRepositories.BudgetPlanRepository;
import com.financetracker.finance.domain.FinanceRepositories.TransactionRepository;
import com.financetracker.finance.domain.Transaction;
import com.financetracker.notifications.api.InAppNotifications;
import com.financetracker.notifications.api.PlanEmailSummary;
import com.financetracker.notifications.api.TransactionalEmails;
import com.financetracker.shared.locale.ExchangeRates;
import com.financetracker.shared.web.Py;

/**
 * Port of budgeting/plan_triggers.py: when to suggest a new plan and how the user is told
 * (in-app notification + email). Each (user, month, reason) notifies at most once.
 */
@Service
public class PlanTriggerService {

    private static final Logger log = LoggerFactory.getLogger(PlanTriggerService.class);
    static final BigDecimal INCOME_DRIFT = new BigDecimal("0.10");
    static final BigDecimal OVERSPEND_RATIO = new BigDecimal("0.80");
    static final int OVERSPEND_FROM_DAY = 15;

    private final PlanningService planning;
    private final BudgetPlanRepository plans;
    private final TransactionRepository transactions;
    private final UserDirectory users;
    private final InAppNotifications inbox;
    private final TransactionalEmails emails;
    private final ExchangeRates rates;
    private final Clock clock;

    public PlanTriggerService(PlanningService planning, BudgetPlanRepository plans, TransactionRepository transactions,
            UserDirectory users, InAppNotifications inbox, TransactionalEmails emails, ExchangeRates rates, Clock clock) {
        this.planning = planning;
        this.plans = plans;
        this.transactions = transactions;
        this.users = users;
        this.inbox = inbox;
        this.emails = emails;
        this.rates = rates;
        this.clock = clock;
    }

    static String monthName(int month) {
        return java.time.Month.of(month).getDisplayName(TextStyle.FULL, Locale.ENGLISH);
    }

    private String preferredType(String userId, boolean hasHistory) {
        Optional<BudgetPlan> accepted = plans.listByUser(userId, 50).stream()
                .filter(p -> "accepted".equals(p.status)).findFirst();
        if (accepted.isPresent()) {
            return accepted.get().planType;
        }
        return hasHistory ? "spending_based" : "rule_50_30_20";
    }

    @SuppressWarnings("unchecked")
    private boolean notifyUser(String userId, String kind, String title, String body, String link, String relatedId,
            String fingerprint, Map<String, Object> plan) {
        if (inbox.exists(userId, fingerprint)) {
            return false;
        }
        inbox.notify(userId, kind, title, body, link, relatedId == null ? "" : relatedId, fingerprint);
        if (plan != null) {
            try {
                Optional<UserSummary> user = users.findById(userId);
                if (user.isPresent()) {
                    PlanEmailSummary summary = new PlanEmailSummary(
                            (int) plan.get("year"), (int) plan.get("month"), (String) plan.get("currency"),
                            (BigDecimal) plan.get("income_total"), (BigDecimal) plan.get("commitments_total"),
                            (BigDecimal) plan.get("needs_total"), (BigDecimal) plan.get("wants_total"),
                            (BigDecimal) plan.get("savings_amount"), String.valueOf(plan.getOrDefault("savings_pct", 0)),
                            (List<String>) plan.getOrDefault("warnings", List.of()));
                    emails.planSuggestion(CommitmentScheduleService.recipient(user.get()), summary, title, body, link);
                }
            } catch (RuntimeException e) {
                log.warn("Plan suggestion email failed for user {}", userId, e);
            }
        }
        return true;
    }

    /** Save a suggested plan and notify. Returns true when a notification was sent. */
    public boolean suggestPlan(String userId, int year, int month, String reason, String title, String body,
            String fingerprint) {
        ProfileSettings settings = users.profileSettings(userId);
        if (!settings.notifyPlanUpdates() || inbox.exists(userId, fingerprint)) {
            return false;
        }
        String currency = users.reportCurrency(userId, null);
        if (planning.expectedIncome(userId, currency).signum() <= 0) {
            return notifyUser(userId, "plan_needs_income", "Add your income to get a budget plan",
                    "Enter your expected monthly income and we will suggest a plan that covers your commitments.",
                    "/budgeting/plan", "", userId + "|needs-income|" + year + "-" + String.format("%02d", month), null);
        }
        PlanningService.History history = planning.spendingByGroup(userId, year, month, currency);
        Map<String, Object> plan = planning.buildPlan(userId, year, month,
                preferredType(userId, history.monthsWithData() > 0), currency, settings.savingsTargetPct());
        BudgetPlan saved = planning.savePlan(userId, plan, reason);
        Map<String, Object> stored = planning.planToMap(saved);
        return notifyUser(userId, "plan_suggested", title, body, "/budgeting/plan?id=" + saved.id, saved.id,
                fingerprint, stored);
    }

    public boolean checkMonthly(String userId, LocalDate today) {
        boolean hasPlan = plans.listForMonth(userId, today.getYear(), today.getMonthValue()).stream()
                .anyMatch(p -> "suggested".equals(p.status) || "accepted".equals(p.status));
        if (hasPlan) {
            return false;
        }
        String label = monthName(today.getMonthValue()) + " " + today.getYear();
        return suggestPlan(userId, today.getYear(), today.getMonthValue(), "monthly",
                "Your budget plan for " + label + " is ready",
                "Here is a suggested plan for " + label + " based on your income and the commitments due this month.",
                userId + "|" + today.getYear() + "-" + String.format("%02d", today.getMonthValue()) + "|monthly");
    }

    /** Last full month's actual income differs from the expected income by more than 10%. */
    public boolean checkIncomeChange(String userId, LocalDate today) {
        String currency = users.reportCurrency(userId, null);
        BigDecimal expected = planning.expectedIncome(userId, currency);
        int[] prev = PlanningService.monthShift(today.getYear(), today.getMonthValue(), -1);
        BigDecimal actual = planning.actualIncome(userId, prev[0], prev[1], currency);
        if (expected.signum() <= 0 || actual.signum() <= 0
                || Dec.div(actual.subtract(expected).abs(), expected).compareTo(INCOME_DRIFT) <= 0) {
            return false;
        }
        String moreOrLess = actual.compareTo(expected) > 0 ? "more" : "less";
        return suggestPlan(userId, today.getYear(), today.getMonthValue(), "income_change",
                "Your income changed: review your budget plan",
                "You received " + Dec.thousands0(actual) + " " + currency + " in " + monthName(prev[1]) + ", " + moreOrLess
                        + " than the " + Dec.thousands0(expected) + " " + currency + " you expect. Update your income if "
                        + "this is the new normal, and review the updated plan.",
                userId + "|" + today.getYear() + "-" + String.format("%02d", today.getMonthValue()) + "|income_change");
    }

    /** From mid-month: at the current pace, savings will fall below 80% of the accepted plan. */
    public boolean checkOverspending(String userId, LocalDate today) {
        if (today.getDayOfMonth() < OVERSPEND_FROM_DAY || !users.profileSettings(userId).notifyPlanUpdates()) {
            return false;
        }
        Optional<BudgetPlan> accepted = plans.listForMonth(userId, today.getYear(), today.getMonthValue()).stream()
                .filter(p -> "accepted".equals(p.status)).findFirst();
        if (accepted.isEmpty()) {
            return false;
        }
        Map<String, Object> plan = planning.planToMap(accepted.get());
        BigDecimal plannedSavings = (BigDecimal) plan.get("savings_amount");
        if (plannedSavings.signum() <= 0) {
            return false;
        }
        String currency = (String) plan.get("currency");
        BigDecimal spent = Dec.ZERO;
        for (Transaction t : transactions.listByUser(userId, ReportService.monthStr(today.getYear(), today.getMonthValue()), 5000)) {
            if ("expense".equals(t.direction) && !ReportService.excludedFromUtilization(t)) {
                spent = spent.add(rates.convertIfNeeded(Dec.orZero(t.amount),
                        t.currency == null || t.currency.isEmpty() ? "USD" : t.currency, currency));
            }
        }
        int days = today.lengthOfMonth();
        BigDecimal projected = ((BigDecimal) plan.get("available"))
                .subtract(Dec.mul(Dec.div(spent, today.getDayOfMonth()), BigDecimal.valueOf(days)))
                .subtract((BigDecimal) plan.get("invested_total"));
        if (projected.compareTo(Dec.mul(plannedSavings, OVERSPEND_RATIO)) >= 0) {
            return false;
        }
        String projectedText = projected.signum() > 0 ? Dec.thousands0(projected) : "0";
        return notifyUser(userId, "plan_overspending", "You are spending faster than planned",
                "At this pace you will save about " + projectedText + " " + currency + " this month instead of "
                        + Dec.thousands0(plannedSavings) + ". Check which categories are running ahead.",
                "/budgeting/plan?id=" + accepted.get().id, accepted.get().id,
                userId + "|" + today.getYear() + "-" + String.format("%02d", today.getMonthValue()) + "|overspending", null);
    }

    /** Called after commitment create/update/delete: the month's fixed costs changed. */
    public boolean onCommitmentChange(String userId, String commitmentId, String action, String name) {
        LocalDate today = LocalDate.now(clock);
        String what = switch (action) {
            case "created" -> "added";
            case "deleted" -> "removed";
            case "updated" -> "changed";
            default -> "changed";
        };
        String label = name == null || name.isEmpty() ? "your loan" : name;
        try {
            return suggestPlan(userId, today.getYear(), today.getMonthValue(), "commitment_change",
                    "Commitments changed: updated budget plan",
                    "The commitment " + label + " was " + what + ", so the money left after commitments changed. "
                            + "Here is an updated plan.",
                    userId + "|" + today.getYear() + "-" + String.format("%02d", today.getMonthValue()) + "|commitment|"
                            + commitmentId + "|" + action);
        } catch (RuntimeException e) {
            log.warn("Plan suggestion after commitment change failed for user {}", userId, e);
            return false;
        }
    }

    public Map<String, Boolean> reviewUser(String userId, LocalDate today) {
        Map<String, Boolean> out = new LinkedHashMap<>();
        out.put("monthly", checkMonthly(userId, today));
        out.put("income_change", checkIncomeChange(userId, today));
        out.put("overspending", checkOverspending(userId, today));
        return out;
    }

    /** review_budget_plans for every active user. */
    public Map<String, Integer> reviewAll() {
        LocalDate today = LocalDate.now(clock);
        Map<String, Integer> totals = new LinkedHashMap<>();
        for (String k : List.of("users", "monthly", "income_change", "overspending", "errors")) {
            totals.put(k, 0);
        }
        for (UserSummary u : users.findAll()) {
            if (!u.active()) {
                continue;
            }
            totals.merge("users", 1, Integer::sum);
            try {
                reviewUser(u.userId(), today).forEach((k, sent) -> totals.merge(k, sent ? 1 : 0, Integer::sum));
            } catch (RuntimeException e) {
                totals.merge("errors", 1, Integer::sum);
                log.warn("user {}: {}", u.id(), Py.str(e.getMessage()));
            }
        }
        return totals;
    }
}
