package com.financetracker.finance.application;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Service;

import com.financetracker.finance.domain.Budget;
import com.financetracker.finance.domain.BudgetPlan;
import com.financetracker.finance.domain.Category;
import com.financetracker.finance.domain.CategoryGroup;
import com.financetracker.finance.domain.Commitment;
import com.financetracker.finance.domain.FinanceRepositories.BudgetPlanRepository;
import com.financetracker.finance.domain.FinanceRepositories.BudgetRepository;
import com.financetracker.finance.domain.FinanceRepositories.CommitmentRepository;
import com.financetracker.finance.domain.FinanceRepositories.GroupBucketRepository;
import com.financetracker.finance.domain.FinanceRepositories.IncomeStreamRepository;
import com.financetracker.finance.domain.FinanceRepositories.SavingsRepository;
import com.financetracker.finance.domain.FinanceRepositories.ScheduleLineRepository;
import com.financetracker.finance.domain.FinanceRepositories.TransactionRepository;
import com.financetracker.finance.domain.GroupBucket;
import com.financetracker.finance.domain.IncomeStream;
import com.financetracker.finance.domain.Savings;
import com.financetracker.finance.domain.ScheduleLine;
import com.financetracker.finance.domain.Transaction;
import com.financetracker.shared.locale.ExchangeRates;
import com.financetracker.shared.web.Py;

/**
 * Port of budgeting/planning.py. Invariant: savings_amount = available - sum(line amounts), where
 * available = expected income - commitment installments due that month.
 */
@Service
public class PlanningService {

    public static final List<String> PLAN_TYPES = List.of("rule_50_30_20", "spending_based");
    public static final Map<String, String> PLAN_LABELS = Map.of(
            "rule_50_30_20", "50/30/20", "spending_based", "Based on your spending");
    public static final List<String> BUCKETS = List.of("needs", "wants", "savings");
    static final int HISTORY_MONTHS = 3;
    static final BigDecimal MAX_WANTS_TRIM = new BigDecimal("0.30");
    static final List<String> NEEDS_KEYWORDS = List.of(
            "home", "house", "housing", "rent", "mortgage", "utilit", "electric", "water", "gas", "internet",
            "phone", "grocer", "food", "supermarket", "transport", "fuel", "car", "health", "medical",
            "pharmacy", "insurance", "education", "school", "tuition", "child", "loan", "debt");
    static final Map<String, BigDecimal> FREQ_PER_MONTH = Map.of(
            "monthly", BigDecimal.ONE,
            "weekly", Dec.div(new BigDecimal("52"), new BigDecimal("12")),
            "biweekly", Dec.div(new BigDecimal("26"), new BigDecimal("12")),
            "yearly", Dec.div(BigDecimal.ONE, new BigDecimal("12")));

    /** Thrown for plan rule violations (Python ValueError) — shown as {"detail": message}. */
    public static class PlanError extends RuntimeException {
        public PlanError(String message) {
            super(message);
        }
    }

    private record Alloc(BigDecimal amount, String basis) {
    }

    private final IncomeStreamRepository incomeStreams;
    private final TransactionRepository transactions;
    private final CommitmentRepository commitments;
    private final ScheduleLineRepository scheduleLines;
    private final GroupBucketRepository groupBuckets;
    private final BudgetRepository budgets;
    private final BudgetPlanRepository plans;
    private final SavingsRepository savings;
    private final CategoryAccess categoryAccess;
    private final AlertService alerts;
    private final ExchangeRates rates;
    private final Clock clock;

    public PlanningService(IncomeStreamRepository incomeStreams, TransactionRepository transactions,
            CommitmentRepository commitments, ScheduleLineRepository scheduleLines, GroupBucketRepository groupBuckets,
            BudgetRepository budgets, BudgetPlanRepository plans, SavingsRepository savings, CategoryAccess categoryAccess,
            AlertService alerts, ExchangeRates rates, Clock clock) {
        this.incomeStreams = incomeStreams;
        this.transactions = transactions;
        this.commitments = commitments;
        this.scheduleLines = scheduleLines;
        this.groupBuckets = groupBuckets;
        this.budgets = budgets;
        this.plans = plans;
        this.savings = savings;
        this.categoryAccess = categoryAccess;
        this.alerts = alerts;
        this.rates = rates;
        this.clock = clock;
    }

    static BigDecimal roundStep(String currency) {
        return "LBP".equalsIgnoreCase(currency == null ? "" : currency) ? new BigDecimal("1000") : BigDecimal.ONE;
    }

    /** Round to whole units (thousands for LBP), ROUND_HALF_UP, shown with 2 decimals. */
    public static BigDecimal moneyRound(BigDecimal value, String currency) {
        BigDecimal step = roundStep(currency);
        BigDecimal units = Dec.div(value, step).setScale(0, RoundingMode.HALF_UP);
        return Dec.q(Dec.mul(units, step), 2);
    }

    /** (year, month) shifted by delta months. */
    public static int[] monthShift(int year, int month, int delta) {
        int idx = year * 12 + (month - 1) + delta;
        return new int[] {Math.floorDiv(idx, 12), Math.floorMod(idx, 12) + 1};
    }

    // ---------------------------------------------------------------- inputs

    public static BigDecimal streamMonthlyAmount(IncomeStream s) {
        BigDecimal factor = FREQ_PER_MONTH.getOrDefault(s.frequency == null || s.frequency.isEmpty() ? "monthly" : s.frequency,
                BigDecimal.ONE);
        return Dec.mul(Dec.orZero(s.amount), factor);
    }

    public BigDecimal expectedIncome(String userId, String currency) {
        BigDecimal total = Dec.ZERO;
        for (IncomeStream s : incomeStreams.listByUser(userId)) {
            if (s.active) {
                total = total.add(rates.convertIfNeeded(streamMonthlyAmount(s),
                        s.currency == null || s.currency.isEmpty() ? "USD" : s.currency, currency));
            }
        }
        return total;
    }

    public BigDecimal actualIncome(String userId, int year, int month, String currency) {
        BigDecimal total = Dec.ZERO;
        for (Transaction t : transactions.listByUser(userId, ReportService.monthStr(year, month), 5000)) {
            if ("income".equals(t.direction)) {
                total = total.add(rates.convertIfNeeded(Dec.orZero(t.amount),
                        t.currency == null || t.currency.isEmpty() ? "USD" : t.currency, currency));
            }
        }
        return total;
    }

    /** All installments due in the month (paid or not): the month's fixed costs. */
    private BigDecimal commitmentsDue(String userId, int year, int month, String currency, List<Map<String, Object>> items) {
        LocalDate start = LocalDate.of(year, month, 1);
        LocalDate end = start.withDayOfMonth(start.lengthOfMonth());
        BigDecimal total = Dec.ZERO;
        for (Commitment c : commitments.listByUser(userId)) {
            BigDecimal amount = Dec.ZERO;
            for (ScheduleLine line : scheduleLines.listByCommitment(c.id)) {
                if (line.dueDate != null && !line.dueDate.isBefore(start) && !line.dueDate.isAfter(end)) {
                    amount = amount.add(rates.convertIfNeeded(line.amount,
                            c.currency == null || c.currency.isEmpty() ? "USD" : c.currency, currency));
                }
            }
            if (amount.signum() != 0) {
                total = total.add(amount);
                Map<String, Object> item = new LinkedHashMap<>();
                item.put("commitment_id", c.id);
                item.put("name", c.name);
                item.put("amount", amount);
                items.add(item);
            }
        }
        return total;
    }

    public static String defaultBucket(String groupName) {
        String name = groupName == null ? "" : groupName.toLowerCase(Locale.ROOT);
        return NEEDS_KEYWORDS.stream().anyMatch(name::contains) ? "needs" : "wants";
    }

    /** group id -> bucket (saved choice, else guessed from the group name). */
    public Map<String, String> groupBuckets(String userId, List<CategoryGroup> groups) {
        Map<String, String> saved = new LinkedHashMap<>();
        for (GroupBucket b : groupBuckets.listByUser(userId)) {
            saved.put(b.groupId, b.bucket);
        }
        Map<String, String> out = new LinkedHashMap<>();
        for (CategoryGroup g : groups) {
            String s = saved.get(g.id);
            out.put(g.id, s != null && !s.isEmpty() ? s : defaultBucket(g.name));
        }
        return out;
    }

    /** Visible groups with at least one reported subcategory, by (order, name). */
    public List<CategoryGroup> plannableGroups(String userId) {
        Set<String> withSubs = new HashSet<>();
        for (Category c : categoryAccess.visibleCategories(userId)) {
            if (c.includeInReports) {
                withSubs.add(c.groupId);
            }
        }
        List<CategoryGroup> groups = new ArrayList<>(categoryAccess.visibleGroups(userId).stream()
                .filter(g -> withSubs.contains(g.id)).toList());
        groups.sort(Comparator.comparingInt((CategoryGroup g) -> g.order).thenComparing(g -> g.name.toLowerCase(Locale.ROOT)));
        return groups;
    }

    /** (average monthly spending per group over the 3 months before (year, month), months with data). */
    public record History(Map<String, BigDecimal> averages, int monthsWithData) {
    }

    public History spendingByGroup(String userId, int year, int month, String currency) {
        Map<String, String> catGroup = new LinkedHashMap<>();
        for (Category c : categoryAccess.visibleCategories(userId)) {
            catGroup.put(c.id, c.groupId);
        }
        Map<String, BigDecimal> totals = new LinkedHashMap<>();
        int monthsWithData = 0;
        for (int back = 1; back <= HISTORY_MONTHS; back++) {
            int[] ym = monthShift(year, month, -back);
            boolean found = false;
            for (Transaction t : transactions.listByUser(userId, ReportService.monthStr(ym[0], ym[1]), 5000)) {
                if (!"expense".equals(t.direction) || ReportService.excludedFromUtilization(t)) {
                    continue;
                }
                String gid = catGroup.get(t.categoryId == null ? "" : t.categoryId);
                if (gid == null || gid.isEmpty()) {
                    continue;
                }
                found = true;
                BigDecimal amt = rates.convertIfNeeded(Dec.orZero(t.amount),
                        t.currency == null || t.currency.isEmpty() ? "USD" : t.currency, currency);
                totals.merge(gid, amt, BigDecimal::add);
            }
            monthsWithData += found ? 1 : 0;
        }
        if (monthsWithData == 0) {
            return new History(Map.of(), 0);
        }
        Map<String, BigDecimal> avg = new LinkedHashMap<>();
        int n = monthsWithData;
        totals.forEach((gid, v) -> avg.put(gid, Dec.div(v, n)));
        return new History(avg, monthsWithData);
    }

    /** Effective forecast per group: explicit group budget if > 0, else the sum of subcategory budgets. */
    public Map<String, BigDecimal> currentForecasts(String userId, int year, int month) {
        Map<String, String> catGroup = new LinkedHashMap<>();
        for (Category c : categoryAccess.visibleCategories(userId)) {
            catGroup.put(c.id, c.groupId);
        }
        Map<String, BigDecimal> explicit = new LinkedHashMap<>();
        Map<String, BigDecimal> fromSubs = new LinkedHashMap<>();
        for (Budget b : budgets.listByUser(userId, year, month)) {
            if (b.categoryId != null && !b.categoryId.strip().isEmpty()) {
                String gid = catGroup.get(b.categoryId);
                if (gid != null && !gid.isEmpty()) {
                    fromSubs.merge(gid, Dec.orZero(b.forecast), BigDecimal::add);
                }
            } else if (b.groupId != null && !b.groupId.strip().isEmpty()) {
                explicit.put(b.groupId, Dec.orZero(b.forecast));
            }
        }
        Map<String, BigDecimal> merged = new LinkedHashMap<>(fromSubs);
        merged.putAll(explicit);
        Map<String, BigDecimal> out = new LinkedHashMap<>();
        merged.forEach((gid, v) -> out.put(gid, v.signum() > 0 ? v : fromSubs.getOrDefault(gid, Dec.ZERO)));
        return out;
    }

    // ---------------------------------------------------------------- allocation

    /** Split total across groups by weight (equally when there are no weights). */
    private static Map<String, BigDecimal> split(BigDecimal total, List<String> groupIds, Map<String, BigDecimal> weights) {
        Map<String, BigDecimal> out = new LinkedHashMap<>();
        if (groupIds.isEmpty() || total.signum() <= 0) {
            groupIds.forEach(g -> out.put(g, Dec.ZERO));
            return out;
        }
        Map<String, BigDecimal> w = new LinkedHashMap<>();
        BigDecimal wsum = Dec.ZERO;
        for (String g : groupIds) {
            BigDecimal v = Dec.max(weights.getOrDefault(g, Dec.ZERO), Dec.ZERO);
            w.put(g, v);
            wsum = wsum.add(v);
        }
        if (wsum.signum() <= 0) {
            for (String g : groupIds) {
                out.put(g, Dec.div(total, groupIds.size()));
            }
            return out;
        }
        for (String g : groupIds) {
            out.put(g, Dec.div(Dec.mul(total, w.get(g)), wsum));
        }
        return out;
    }

    /** int((part / whole * 100).quantize(Decimal("1"))) if whole > 0 else 0 */
    static int pct(BigDecimal part, BigDecimal whole) {
        return whole.signum() > 0 ? Dec.q(Dec.mul(Dec.div(part, whole), Dec.HUNDRED), 0).intValueExact() : 0;
    }

    /** Commitments count as needs; if they crowd out living costs, shift to 60/25/15. */
    private static Map<String, Alloc> rule503020(BigDecimal income, BigDecimal commitments, BigDecimal available,
            Map<String, String> buckets, Map<String, BigDecimal> history, List<String> warnings) {
        Map<String, List<String>> ids = new LinkedHashMap<>();
        for (String b : BUCKETS) {
            List<String> list = new ArrayList<>();
            buckets.forEach((g, bk) -> {
                if (b.equals(bk)) {
                    list.add(g);
                }
            });
            ids.put(b, list);
        }
        BigDecimal histNeeds = Dec.ZERO;
        for (String g : ids.get("needs")) {
            histNeeds = histNeeds.add(history.getOrDefault(g, Dec.ZERO));
        }
        BigDecimal needsR = new BigDecimal("0.50");
        BigDecimal wantsR = new BigDecimal("0.30");
        BigDecimal saveR = new BigDecimal("0.20");
        BigDecimal floor = Dec.max(histNeeds, Dec.mul(income, new BigDecimal("0.15")));
        if (Dec.mul(income, needsR).subtract(commitments).compareTo(floor) < 0) {
            needsR = new BigDecimal("0.60");
            wantsR = new BigDecimal("0.25");
            saveR = new BigDecimal("0.15");
            warnings.add("Commitments take " + pct(commitments, income) + "% of income, so this plan uses a "
                    + "debt-aware 60/25/15 split instead of 50/30/20.");
        }
        BigDecimal needsLeft = Dec.mul(income, needsR).subtract(commitments);
        BigDecimal wants = Dec.mul(income, wantsR);
        if (needsLeft.compareTo(floor) < 0) {
            needsLeft = floor;
            wants = Dec.max(available.subtract(needsLeft).subtract(Dec.mul(income, new BigDecimal("0.05"))), Dec.ZERO);
            warnings.add("Income after commitments is tight: wants are reduced to keep essentials covered.");
        }
        Map<String, BigDecimal> alloc = new LinkedHashMap<>();
        alloc.putAll(split(Dec.max(needsLeft, Dec.ZERO), ids.get("needs"), history));
        alloc.putAll(split(wants, ids.get("wants"), history));
        BigDecimal saveShare = Dec.mul(income, saveR);
        for (String gid : ids.get("savings")) {
            BigDecimal v = Dec.min(history.getOrDefault(gid, Dec.ZERO), saveShare);
            alloc.put(gid, v);
            saveShare = saveShare.subtract(v);
        }
        Map<String, Alloc> out = new LinkedHashMap<>();
        alloc.forEach((g, v) -> out.put(g, new Alloc(v, "rule")));
        return out;
    }

    /** Start from recent averages; trim wants (at most 30% each) towards the savings target. */
    private static Map<String, Alloc> spendingBased(BigDecimal income, BigDecimal available, Map<String, String> buckets,
            Map<String, BigDecimal> history, int savingsPct, List<String> warnings) {
        BigDecimal target = Dec.div(Dec.mul(income, BigDecimal.valueOf(savingsPct)), 100);
        Map<String, Alloc> alloc = new LinkedHashMap<>();
        buckets.keySet().forEach(g -> alloc.put(g, new Alloc(history.getOrDefault(g, Dec.ZERO), "history")));
        BigDecimal spend = Dec.ZERO;
        for (Alloc a : alloc.values()) {
            spend = spend.add(a.amount());
        }
        BigDecimal shortfall = spend.add(target).subtract(available);
        if (shortfall.signum() > 0) {
            Map<String, BigDecimal> wants = new LinkedHashMap<>();
            buckets.forEach((g, b) -> {
                if ("wants".equals(b) && alloc.get(g).amount().signum() > 0) {
                    wants.put(g, alloc.get(g).amount());
                }
            });
            BigDecimal wantsSum = Dec.ZERO;
            for (BigDecimal v : wants.values()) {
                wantsSum = wantsSum.add(v);
            }
            BigDecimal maxTrim = Dec.mul(wantsSum, MAX_WANTS_TRIM);
            BigDecimal trim = Dec.min(shortfall, maxTrim);
            split(trim, new ArrayList<>(wants.keySet()), wants)
                    .forEach((g, amt) -> alloc.put(g, new Alloc(alloc.get(g).amount().subtract(amt), "trimmed")));
            if (trim.signum() != 0) {
                warnings.add("Wants are trimmed to move closer to your " + savingsPct + "% savings target.");
            }
            if (shortfall.subtract(trim).signum() > 0) {
                warnings.add("Your usual spending leaves less than your " + savingsPct
                        + "% savings target even after trimming wants.");
            }
        }
        return alloc;
    }

    /** Compute a plan (not saved); amounts in `currency`. */
    public Map<String, Object> buildPlan(String userId, int year, int month, String planType, String currency, int savingsPct) {
        if (!PLAN_TYPES.contains(planType)) {
            throw new PlanError("Unknown plan type.");
        }
        List<String> warnings = new ArrayList<>();
        BigDecimal income = expectedIncome(userId, currency);
        List<Map<String, Object>> commitmentItems = new ArrayList<>();
        BigDecimal commitmentsTotal = commitmentsDue(userId, year, month, currency, commitmentItems);
        BigDecimal available = income.subtract(commitmentsTotal);
        List<CategoryGroup> groups = plannableGroups(userId);
        Map<String, String> buckets = groupBuckets(userId, groups);
        History history = spendingByGroup(userId, year, month, currency);
        Map<String, BigDecimal> current = currentForecasts(userId, year, month);

        String effectiveType = planType;
        Map<String, Alloc> alloc;
        if (income.signum() <= 0) {
            warnings.add("Add your expected income to get a plan.");
            alloc = new LinkedHashMap<>();
            for (CategoryGroup g : groups) {
                alloc.put(g.id, new Alloc(Dec.ZERO, "rule"));
            }
        } else if ("spending_based".equals(planType) && history.monthsWithData() == 0) {
            warnings.add("No spending history in the last 3 months yet, so this uses the 50/30/20 split.");
            effectiveType = "rule_50_30_20";
            alloc = rule503020(income, commitmentsTotal, available, buckets, history.averages(), warnings);
        } else if ("spending_based".equals(planType)) {
            alloc = spendingBased(income, available, buckets, history.averages(), savingsPct, warnings);
        } else {
            alloc = rule503020(income, commitmentsTotal, available, buckets, history.averages(), warnings);
        }

        List<Map<String, Object>> lines = new ArrayList<>();
        for (CategoryGroup g : groups) {
            Alloc a = alloc.getOrDefault(g.id, new Alloc(Dec.ZERO, "rule"));
            Map<String, Object> line = new LinkedHashMap<>();
            line.put("group_id", g.id);
            line.put("group_name", g.name);
            line.put("bucket", buckets.get(g.id));
            line.put("amount", moneyRound(Dec.max(a.amount(), Dec.ZERO), currency));
            line.put("average_spend", moneyRound(history.averages().getOrDefault(g.id, Dec.ZERO), currency));
            line.put("current_forecast", current.getOrDefault(g.id, Dec.ZERO));
            line.put("basis", a.basis());
            lines.add(line);
        }
        if (commitmentsTotal.signum() > 0 && income.signum() > 0 && commitmentsTotal.compareTo(income) >= 0) {
            warnings.add("Commitments due this month are more than your income.");
        }
        Map<String, Object> plan = new LinkedHashMap<>();
        plan.put("year", year);
        plan.put("month", month);
        plan.put("plan_type", planType);
        plan.put("effective_type", effectiveType);
        plan.put("label", PLAN_LABELS.get(planType));
        plan.put("currency", currency);
        plan.put("income_total", moneyRound(income, currency));
        plan.put("commitments_total", moneyRound(commitmentsTotal, currency));
        List<Map<String, Object>> rounded = new ArrayList<>();
        for (Map<String, Object> item : commitmentItems) {
            Map<String, Object> copy = new LinkedHashMap<>(item);
            copy.put("amount", moneyRound((BigDecimal) item.get("amount"), currency));
            rounded.add(copy);
        }
        plan.put("commitments", rounded);
        plan.put("history_months", history.monthsWithData());
        plan.put("savings_target_pct", savingsPct);
        plan.put("lines", lines);
        plan.put("warnings", warnings);
        return recomputeTotals(plan);
    }

    private static BigDecimal toDec(Object v) {
        if (v instanceof BigDecimal bd) {
            return bd;
        }
        return new BigDecimal(Py.str(v));
    }

    /** Derive available, bucket totals and savings from income, commitments and lines. */
    @SuppressWarnings("unchecked")
    public static Map<String, Object> recomputeTotals(Map<String, Object> plan) {
        BigDecimal income = toDec(plan.get("income_total"));
        BigDecimal commitmentsTotal = toDec(plan.get("commitments_total"));
        plan.put("available", income.subtract(commitmentsTotal));
        Map<String, BigDecimal> totals = new LinkedHashMap<>();
        BUCKETS.forEach(b -> totals.put(b, Dec.ZERO));
        for (Map<String, Object> line : (List<Map<String, Object>>) plan.get("lines")) {
            BigDecimal amount = toDec(line.get("amount"));
            line.put("amount", amount);
            Object bucket = line.get("bucket");
            String key = bucket != null && totals.containsKey(String.valueOf(bucket)) ? String.valueOf(bucket) : "wants";
            totals.merge(key, amount, BigDecimal::add);
        }
        plan.put("needs_total", totals.get("needs"));
        plan.put("wants_total", totals.get("wants"));
        plan.put("invested_total", totals.get("savings"));
        BigDecimal all = totals.get("needs").add(totals.get("wants")).add(totals.get("savings"));
        BigDecimal savingsAmount = ((BigDecimal) plan.get("available")).subtract(all);
        plan.put("savings_amount", savingsAmount);
        plan.put("savings_pct", pct(Dec.max(savingsAmount.add(totals.get("savings")), Dec.ZERO), income));
        return plan;
    }

    // ---------------------------------------------------------------- persistence

    private static List<Map<String, Object>> jsonLines(List<Map<String, Object>> lines) {
        List<Map<String, Object>> out = new ArrayList<>();
        for (Map<String, Object> line : lines) {
            Map<String, Object> copy = new LinkedHashMap<>(line);
            for (String k : List.of("amount", "average_spend", "current_forecast")) {
                if (copy.containsKey(k)) {
                    Object v = copy.get(k);
                    copy.put(k, v instanceof BigDecimal bd ? Py.dec(bd) : Py.str(v));
                }
            }
            out.add(copy);
        }
        return out;
    }

    /** Store a computed plan as a suggestion; older pending suggestions for that month are superseded. */
    @SuppressWarnings("unchecked")
    public BudgetPlan savePlan(String userId, Map<String, Object> plan, String reason) {
        int year = (int) plan.get("year");
        int month = (int) plan.get("month");
        for (BudgetPlan old : plans.listForMonth(userId, year, month)) {
            if ("suggested".equals(old.status)) {
                old.status = "superseded";
                plans.save(old);
            }
        }
        BudgetPlan p = new BudgetPlan();
        p.userId = userId;
        p.year = year;
        p.month = month;
        p.planType = (String) plan.get("plan_type");
        p.status = "suggested";
        p.reason = reason;
        p.currency = (String) plan.get("currency");
        p.incomeTotal = (BigDecimal) plan.get("income_total");
        p.commitmentsTotal = (BigDecimal) plan.get("commitments_total");
        p.available = (BigDecimal) plan.get("available");
        p.needsTotal = (BigDecimal) plan.get("needs_total");
        p.wantsTotal = (BigDecimal) plan.get("wants_total");
        p.savingsAmount = (BigDecimal) plan.get("savings_amount");
        p.lines = jsonLines((List<Map<String, Object>>) plan.get("lines"));
        p.warnings = new ArrayList<>((List<String>) plan.getOrDefault("warnings", List.of()));
        plans.save(p);
        return p;
    }

    /** Stored plan -> API map (totals recomputed from the stored lines). */
    public Map<String, Object> planToMap(BudgetPlan p) {
        Map<String, Object> plan = new LinkedHashMap<>();
        plan.put("id", p.id);
        plan.put("year", p.year);
        plan.put("month", p.month);
        plan.put("plan_type", p.planType);
        plan.put("label", PLAN_LABELS.getOrDefault(p.planType, p.planType));
        plan.put("status", p.status);
        plan.put("reason", p.reason);
        plan.put("currency", p.currency);
        plan.put("income_total", p.incomeTotal);
        plan.put("commitments_total", p.commitmentsTotal);
        List<Map<String, Object>> lines = new ArrayList<>();
        for (Map<String, Object> line : p.lines == null ? List.<Map<String, Object>>of() : p.lines) {
            lines.add(new LinkedHashMap<>(line));
        }
        plan.put("lines", lines);
        plan.put("warnings", p.warnings == null ? new ArrayList<>() : new ArrayList<>(p.warnings));
        plan.put("created_at", Py.isoformat(p.createdAt));
        plan.put("accepted_at", Py.isoformat(p.acceptedAt));
        return recomputeTotals(plan);
    }

    /** Apply user edits {group_id: amount}; savings is recomputed from the new lines. */
    public BudgetPlan updateLines(BudgetPlan p, Map<String, Object> amounts) {
        if (!"suggested".equals(p.status)) {
            throw new PlanError("Only a suggested plan can be edited.");
        }
        List<Map<String, Object>> lines = new ArrayList<>();
        for (Map<String, Object> line : p.lines) {
            Map<String, Object> copy = new LinkedHashMap<>(line);
            Object gid = copy.get("group_id");
            if (gid != null && amounts.containsKey(String.valueOf(gid))) {
                BigDecimal value;
                try {
                    value = toDec(amounts.get(String.valueOf(gid)));
                } catch (RuntimeException e) {
                    throw new PlanError("Invalid amount.");
                }
                if (value.signum() < 0) {
                    throw new PlanError("Amounts cannot be negative.");
                }
                copy.put("amount", Py.dec(moneyRound(value, p.currency)));
                copy.put("basis", "edited");
            }
            lines.add(copy);
        }
        p.lines = lines;
        Map<String, Object> totals = planToMap(p);
        p.needsTotal = (BigDecimal) totals.get("needs_total");
        p.wantsTotal = (BigDecimal) totals.get("wants_total");
        p.savingsAmount = (BigDecimal) totals.get("savings_amount");
        plans.save(p);
        return p;
    }

    /** Write the plan into the month's group budgets and savings target. */
    public BudgetPlan accept(String userId, BudgetPlan p) {
        if (!"suggested".equals(p.status) && !"accepted".equals(p.status)) {
            throw new PlanError("This plan was replaced or dismissed; create a new one.");
        }
        for (Map<String, Object> line : p.lines) {
            String gid = String.valueOf(line.get("group_id"));
            Budget b = budgets.getByUserGroupMonth(userId, gid, p.year, p.month).orElseGet(() -> {
                Budget nb = new Budget();
                nb.userId = userId;
                nb.groupId = gid;
                nb.categoryId = "";
                nb.year = p.year;
                nb.month = p.month;
                nb.forecast = Dec.ZERO;
                return nb;
            });
            b.forecast = toDec(line.get("amount"));
            budgets.save(b);
        }
        Map<String, Object> plan = planToMap(p);
        Savings s = savings.getByUserMonth(userId, p.year, p.month).orElseGet(() -> {
            Savings ns = new Savings();
            ns.userId = userId;
            ns.year = p.year;
            ns.month = p.month;
            ns.target = Dec.ZERO;
            ns.goalStatus = "pending";
            return ns;
        });
        s.target = Dec.max(((BigDecimal) plan.get("savings_amount")).add((BigDecimal) plan.get("invested_total")), Dec.ZERO);
        savings.save(s);
        for (BudgetPlan other : plans.listForMonth(userId, p.year, p.month)) {
            if (!other.id.equals(p.id) && ("suggested".equals(other.status) || "accepted".equals(other.status))) {
                other.status = "superseded";
                plans.save(other);
            }
        }
        p.status = "accepted";
        p.acceptedAt = Instant.now(clock);
        plans.save(p);
        alerts.trigger(userId, p.year, p.month);
        return p;
    }
}
