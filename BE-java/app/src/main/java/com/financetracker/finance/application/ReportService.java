package com.financetracker.finance.application;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.function.Function;

import org.springframework.stereotype.Service;

import com.financetracker.finance.domain.Budget;
import com.financetracker.finance.domain.BudgetThreshold;
import com.financetracker.finance.domain.Category;
import com.financetracker.finance.domain.CategoryGroup;
import com.financetracker.finance.domain.Commitment;
import com.financetracker.finance.domain.FinanceRepositories.BudgetRepository;
import com.financetracker.finance.domain.FinanceRepositories.BudgetThresholdRepository;
import com.financetracker.finance.domain.FinanceRepositories.CategoryRepository;
import com.financetracker.finance.domain.FinanceRepositories.CommitmentRepository;
import com.financetracker.finance.domain.FinanceRepositories.MerchantLinkRepository;
import com.financetracker.finance.domain.FinanceRepositories.ScheduleLineRepository;
import com.financetracker.finance.domain.FinanceRepositories.TransactionRepository;
import com.financetracker.finance.domain.MerchantLink;
import com.financetracker.finance.domain.ScheduleLine;
import com.financetracker.finance.domain.Transaction;
import com.financetracker.shared.locale.ExchangeRates;

/** Port of budgeting/services.py: actuals, variance, utilization and yearly reports. */
@Service
public class ReportService {

    public static final String UNMAPPED_CATEGORY_ID = "_unmapped_";
    public static final BigDecimal DEFAULT_WARN_PCT = new BigDecimal("80");
    public static final BigDecimal DEFAULT_CRITICAL_PCT = new BigDecimal("100");

    /** (warn_pct, critical_pct, email_enabled) */
    public record Threshold(BigDecimal warnPct, BigDecimal criticalPct, boolean emailEnabled) {
    }

    private final TransactionRepository transactions;
    private final BudgetRepository budgets;
    private final BudgetThresholdRepository thresholds;
    private final CommitmentRepository commitments;
    private final ScheduleLineRepository scheduleLines;
    private final MerchantLinkRepository merchantLinks;
    private final CategoryRepository categories;
    private final CategoryAccess categoryAccess;
    private final ExchangeRates rates;

    public ReportService(TransactionRepository transactions, BudgetRepository budgets, BudgetThresholdRepository thresholds,
            CommitmentRepository commitments, ScheduleLineRepository scheduleLines, MerchantLinkRepository merchantLinks,
            CategoryRepository categories, CategoryAccess categoryAccess, ExchangeRates rates) {
        this.transactions = transactions;
        this.budgets = budgets;
        this.thresholds = thresholds;
        this.commitments = commitments;
        this.scheduleLines = scheduleLines;
        this.merchantLinks = merchantLinks;
        this.categories = categories;
        this.categoryAccess = categoryAccess;
        this.rates = rates;
    }

    public static String monthStr(LocalDate d) {
        return String.format("%04d-%02d", d.getYear(), d.getMonthValue());
    }

    public static String monthStr(int year, int month) {
        return String.format("%d-%02d", year, month);
    }

    private BigDecimal txnAmount(Transaction t, String reportCurrency) {
        BigDecimal amt = t.amount == null ? Dec.ZERO : t.amount;
        if (reportCurrency != null && !reportCurrency.isEmpty()) {
            return rates.convertIfNeeded(amt, t.currency == null || t.currency.isEmpty() ? "USD" : t.currency, reportCurrency);
        }
        return amt;
    }

    /** _expense_excluded_from_utilization: commitment payments unless explicitly included. */
    public static boolean excludedFromUtilization(Transaction t) {
        if (t.includeInUtilization) {
            return false;
        }
        if (t.commitmentId != null && !t.commitmentId.isEmpty()) {
            return true;
        }
        return t.externalId != null && t.externalId.startsWith("commitment_line:");
    }

    /** Expense per category for a month; commitments optionally excluded. */
    public Map<String, BigDecimal> actualExpenseByCategory(String userId, int year, int month, boolean excludeCommitments,
            String reportCurrency) {
        Map<String, BigDecimal> result = new LinkedHashMap<>();
        for (Transaction t : transactions.listByUser(userId, monthStr(year, month), 500)) {
            if (!"expense".equals(t.direction)) {
                continue;
            }
            if (excludeCommitments && !t.includeInUtilization
                    && ((t.commitmentId != null && !t.commitmentId.isEmpty())
                            || (t.externalId != null && t.externalId.startsWith("commitment_line:")))) {
                continue;
            }
            String cid = t.categoryId == null || t.categoryId.isEmpty() ? UNMAPPED_CATEGORY_ID : t.categoryId;
            result.merge(cid, txnAmount(t, reportCurrency), BigDecimal::add);
        }
        return result;
    }

    public BigDecimal actualIncomeTotal(String userId, int year, int month, String reportCurrency) {
        BigDecimal total = Dec.ZERO;
        for (Transaction t : transactions.listByUser(userId, monthStr(year, month), 500)) {
            if ("income".equals(t.direction)) {
                total = total.add(txnAmount(t, reportCurrency));
            }
        }
        return total;
    }

    public BigDecimal actualExpenseTotal(String userId, int year, int month, String reportCurrency) {
        BigDecimal total = Dec.ZERO;
        for (BigDecimal v : actualExpenseByCategory(userId, year, month, false, reportCurrency).values()) {
            total = total.add(v);
        }
        return total;
    }

    /** Outstanding installments due in the month (paid ones are already expense transactions). */
    public BigDecimal commitmentPaymentsTotal(String userId, int year, int month, String reportCurrency) {
        LocalDate start = LocalDate.of(year, month, 1);
        LocalDate end = start.plusMonths(1);
        BigDecimal total = Dec.ZERO;
        for (Commitment c : commitments.listByUser(userId)) {
            String currency = c.currency == null || c.currency.isEmpty() ? "USD" : c.currency;
            for (ScheduleLine line : scheduleLines.listByCommitment(c.id)) {
                if (!ScheduleLine.OUTSTANDING.equals(line.status) || line.dueDate == null) {
                    continue;
                }
                if (!line.dueDate.isBefore(start) && line.dueDate.isBefore(end)) {
                    total = total.add(rates.convertIfNeeded(line.amount, currency, reportCurrency));
                }
            }
        }
        return total;
    }

    /** income - expenses - outstanding commitment payments for the month. */
    public BigDecimal savingsActual(String userId, int year, int month, String reportCurrency) {
        return actualIncomeTotal(userId, year, month, reportCurrency)
                .subtract(actualExpenseTotal(userId, year, month, reportCurrency))
                .subtract(commitmentPaymentsTotal(userId, year, month, reportCurrency));
    }

    public static BigDecimal variance(BigDecimal actual, BigDecimal forecast) {
        return Dec.orZero(actual).subtract(Dec.orZero(forecast));
    }

    /** (actual / forecast * 100).quantize(0.1), or null without a forecast. */
    public static BigDecimal utilizationPct(BigDecimal actual, BigDecimal forecast) {
        BigDecimal a = Dec.orZero(actual);
        BigDecimal f = Dec.orZero(forecast);
        if (f.signum() != 0) {
            return Dec.q(Dec.mul(Dec.div(a, f), Dec.HUNDRED), 1);
        }
        return null;
    }

    /** ok | warn | critical | over */
    public static String utilizationStatus(BigDecimal util, BigDecimal warnPct, BigDecimal criticalPct) {
        if (util == null) {
            return "ok";
        }
        if (util.compareTo(criticalPct) > 0) {
            return "over";
        }
        if (util.compareTo(criticalPct) >= 0) {
            return "critical";
        }
        if (util.compareTo(warnPct) >= 0) {
            return "warn";
        }
        return "ok";
    }

    /** Threshold lookup for one user: category-specific, else global, else 80/100/email. */
    public Function<String, Threshold> thresholdGetter(String userId) {
        Map<String, BudgetThreshold> byCat = new LinkedHashMap<>();
        BudgetThreshold global = null;
        for (BudgetThreshold t : thresholds.findByUserIdOrderByIdAsc(userId)) {
            if (t.categoryId != null && !t.categoryId.isEmpty()) {
                byCat.put(t.categoryId, t);
            } else {
                global = t;
            }
        }
        BudgetThreshold g = global;
        return categoryId -> {
            BudgetThreshold t = categoryId != null && !categoryId.isEmpty() ? byCat.get(categoryId) : g;
            if (t == null && categoryId != null && !categoryId.isEmpty()) {
                t = g;
            }
            if (t != null) {
                return new Threshold(t.warnPct, t.criticalPct, t.emailEnabled);
            }
            return new Threshold(DEFAULT_WARN_PCT, DEFAULT_CRITICAL_PCT, true);
        };
    }

    /** _threshold_for: BudgetThresholdFS.get_for_category semantics. */
    private Function<String, Threshold> thresholdFor(String userId) {
        List<BudgetThreshold> all = thresholds.findByUserIdOrderByIdAsc(userId);
        return categoryId -> {
            Optional<BudgetThreshold> t = Optional.empty();
            if (categoryId != null && !categoryId.isEmpty()) {
                t = all.stream().filter(x -> categoryId.equals(x.categoryId)).findFirst();
            }
            if (t.isEmpty()) {
                t = all.stream().filter(x -> x.categoryId == null || x.categoryId.isEmpty()).findFirst();
            }
            return t.map(x -> new Threshold(x.warnPct, x.criticalPct, x.emailEnabled))
                    .orElseGet(() -> new Threshold(DEFAULT_WARN_PCT, DEFAULT_CRITICAL_PCT, true));
        };
    }

    /** Month (1-12) a transaction belongs to within `year`, from its month string or date. */
    static Integer txnMonthInYear(Transaction t, int year) {
        String m = t.month == null ? "" : t.month.strip();
        if (m.length() >= 7) {
            try {
                int y = Integer.parseInt(m.substring(0, 4));
                int mo = Integer.parseInt(m.substring(5, 7));
                if (y == year && mo >= 1 && mo <= 12) {
                    return mo;
                }
            } catch (NumberFormatException ignored) {
                // fall through to the date
            }
        }
        if (t.date != null && t.date.getYear() == year) {
            return t.date.getMonthValue();
        }
        return null;
    }

    /** _budget_maps: (group budgets by group id, subcategory budgets by category id). */
    static Map<String, Budget>[] budgetMaps(List<Budget> monthBudgets) {
        Map<String, Budget> groupBudgets = new LinkedHashMap<>();
        Map<String, Budget> catBudgets = new LinkedHashMap<>();
        for (Budget b : monthBudgets) {
            if (b.categoryId != null && !b.categoryId.strip().isEmpty()) {
                catBudgets.put(b.categoryId, b);
            } else if (b.groupId != null && !b.groupId.strip().isEmpty()) {
                groupBudgets.put(b.groupId, b);
            }
        }
        @SuppressWarnings("unchecked")
        Map<String, Budget>[] maps = new Map[] {groupBudgets, catBudgets};
        return maps;
    }

    public static BigDecimal subForecastSum(Map<String, Budget> catBudgets, List<Category> subs) {
        BigDecimal total = Dec.ZERO;
        for (Category c : subs) {
            Budget b = catBudgets.get(c.id);
            if (b != null) {
                total = total.add(Dec.orZero(b.forecast));
            }
        }
        return total;
    }

    /** Explicit group cap when > 0, otherwise the sum of subcategory budgets. */
    public static BigDecimal effectiveGroupForecast(Budget groupBudget, BigDecimal subSum) {
        if (groupBudget != null && Dec.pos(groupBudget.forecast)) {
            return groupBudget.forecast;
        }
        return subSum;
    }

    private static List<Category> reportedSubs(Map<String, Category> categoriesById, String groupId) {
        List<Category> subs = new ArrayList<>();
        for (Category c : categoriesById.values()) {
            if (groupId.equals(c.groupId) && c.includeInReports) {
                subs.add(c);
            }
        }
        return subs;
    }

    private static BigDecimal sumActuals(Map<String, BigDecimal> actuals, List<Category> subs) {
        BigDecimal total = Dec.ZERO;
        for (Category c : subs) {
            total = total.add(Dec.orZero(actuals.get(c.id)));
        }
        return total;
    }

    private static Comparator<CategoryGroup> groupOrder() {
        return Comparator.comparingInt((CategoryGroup g) -> g.order).thenComparing(g -> g.name.toLowerCase(Locale.ROOT));
    }

    private static Comparator<Category> categoryOrder() {
        return Comparator.comparingInt((Category c) -> c.order).thenComparing(c -> c.name.toLowerCase(Locale.ROOT));
    }

    /** _utilization_summary for one month (group-level forecasts, no double counting). */
    private Map<String, Object> utilizationSummary(Map<String, BigDecimal> actuals, List<Budget> monthBudgets,
            Map<String, Category> categoriesById, Function<String, Threshold> thresholdGet, List<CategoryGroup> groups) {
        Map<String, Budget>[] maps = budgetMaps(monthBudgets);
        BigDecimal totalForecast = Dec.ZERO;
        BigDecimal totalActual = Dec.ZERO;
        for (CategoryGroup g : groups) {
            List<Category> subs = reportedSubs(categoriesById, g.id);
            if (subs.isEmpty()) {
                continue;
            }
            BigDecimal subSum = subForecastSum(maps[1], subs);
            BigDecimal effective = effectiveGroupForecast(maps[0].get(g.id), subSum);
            BigDecimal act = sumActuals(actuals, subs);
            if (effective.signum() > 0 || act.signum() > 0) {
                totalForecast = totalForecast.add(effective);
                totalActual = totalActual.add(act);
            }
        }
        BigDecimal unmapped = Dec.orZero(actuals.get(UNMAPPED_CATEGORY_ID));
        if (unmapped.signum() > 0) {
            totalActual = totalActual.add(unmapped);
        }
        BigDecimal overallUtil = utilizationPct(totalActual, totalForecast);
        Threshold global = thresholdGet.apply(null);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("total_forecast", totalForecast);
        out.put("total_actual", totalActual);
        out.put("remaining", totalForecast.subtract(totalActual));
        out.put("overall_util", overallUtil);
        out.put("overall_status", utilizationStatus(overallUtil, global.warnPct(), global.criticalPct()));
        return out;
    }

    /** yearly_overview_report: one load of transactions, budgets and categories for the year. */
    public Map<String, Object> yearlyOverview(String userId, int year, String reportCurrency) {
        Map<Integer, BigDecimal> incomeByMonth = new LinkedHashMap<>();
        Map<Integer, BigDecimal> expenseByMonth = new LinkedHashMap<>();
        Map<Integer, Map<String, BigDecimal>> utilActuals = new LinkedHashMap<>();
        for (int m = 1; m <= 12; m++) {
            incomeByMonth.put(m, Dec.ZERO);
            expenseByMonth.put(m, Dec.ZERO);
            utilActuals.put(m, new LinkedHashMap<>());
        }
        for (Transaction t : transactions.listByUser(userId, null, 2000)) {
            Integer m = txnMonthInYear(t, year);
            if (m == null) {
                continue;
            }
            BigDecimal amt = txnAmount(t, reportCurrency);
            if ("income".equals(t.direction)) {
                incomeByMonth.merge(m, amt, BigDecimal::add);
            } else if ("expense".equals(t.direction)) {
                expenseByMonth.merge(m, amt, BigDecimal::add);
                if (!excludedFromUtilization(t)) {
                    String cid = t.categoryId == null || t.categoryId.isEmpty() ? UNMAPPED_CATEGORY_ID : t.categoryId;
                    utilActuals.get(m).merge(cid, amt, BigDecimal::add);
                }
            }
        }
        CategoryAccess.Visible visible = categoryAccess.forUser(userId);
        Function<String, Threshold> thresholdGet = thresholdGetter(userId);
        Map<Integer, List<Budget>> budgetsByMonth = new LinkedHashMap<>();
        for (int m = 1; m <= 12; m++) {
            budgetsByMonth.put(m, new ArrayList<>());
        }
        for (Budget b : budgets.listByUser(userId, year, null)) {
            if (b.month >= 1 && b.month <= 12) {
                budgetsByMonth.get(b.month).add(b);
            }
        }
        List<Map<String, Object>> months = new ArrayList<>();
        BigDecimal incomeYear = Dec.ZERO;
        BigDecimal expenseYear = Dec.ZERO;
        for (int m = 1; m <= 12; m++) {
            BigDecimal income = incomeByMonth.get(m);
            BigDecimal expense = expenseByMonth.get(m);
            Map<String, Object> summary = utilizationSummary(utilActuals.get(m), budgetsByMonth.get(m),
                    visible.categoriesById(), thresholdGet, visible.groups());
            incomeYear = incomeYear.add(income);
            expenseYear = expenseYear.add(expense);
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("month", m);
            row.put("income_total", income);
            row.put("expense_total", expense);
            row.put("net", income.subtract(expense));
            row.putAll(summary);
            months.add(row);
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("year", year);
        out.put("report_currency", reportCurrency == null || reportCurrency.isEmpty() ? "USD" : reportCurrency);
        out.put("income_total", incomeYear);
        out.put("expense_total", expenseYear);
        out.put("net", incomeYear.subtract(expenseYear));
        out.put("months", months);
        return out;
    }

    /** budget_utilization_report: group rows (cap or sum of subs) with subcategory detail rows. */
    public Map<String, Object> utilizationReport(String userId, int year, int month, String reportCurrency) {
        CategoryAccess.Visible visible = categoryAccess.forUser(userId);
        Map<String, CategoryGroup> groupsMap = new LinkedHashMap<>();
        for (CategoryGroup g : visible.groups()) {
            groupsMap.put(g.id, g);
        }
        Map<String, Budget>[] maps = budgetMaps(budgets.listByUser(userId, year, month));
        Map<String, Budget> groupBudgets = maps[0];
        Map<String, Budget> catBudgets = maps[1];
        Map<String, BigDecimal> actuals = actualExpenseByCategory(userId, year, month, true, reportCurrency);
        Function<String, Threshold> thresholdFor = thresholdFor(userId);

        List<Map<String, Object>> rows = new ArrayList<>();
        List<CategoryGroup> sortedGroups = new ArrayList<>(visible.groups());
        sortedGroups.sort(groupOrder());
        for (CategoryGroup g : sortedGroups) {
            List<Category> subs = reportedSubs(visible.categoriesById(), g.id);
            if (subs.isEmpty()) {
                continue;
            }
            BigDecimal subSum = subForecastSum(catBudgets, subs);
            Budget gb = groupBudgets.get(g.id);
            BigDecimal effective = effectiveGroupForecast(gb, subSum);
            BigDecimal groupActual = sumActuals(actuals, subs);
            boolean hasSubBudgets = subs.stream().anyMatch(c -> catBudgets.containsKey(c.id));
            if (effective.signum() <= 0 && groupActual.signum() <= 0 && gb == null && !hasSubBudgets) {
                continue;
            }
            BigDecimal util = utilizationPct(groupActual, effective);
            Threshold th = thresholdFor.apply(null);
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("category_id", "group:" + g.id);
            row.put("category_name", g.name);
            row.put("group_name", g.name);
            row.put("forecast", effective);
            row.put("forecast_explicit", gb != null && Dec.pos(gb.forecast) ? gb.forecast : null);
            row.put("forecast_from_subs", subSum);
            row.put("actual", groupActual);
            row.put("remaining", effective.subtract(groupActual));
            row.put("variance", variance(groupActual, effective));
            row.put("utilization_pct", util);
            row.put("status", utilizationStatus(util, th.warnPct(), th.criticalPct()));
            row.put("warn_pct", th.warnPct());
            row.put("critical_pct", th.criticalPct());
            row.put("email_enabled", th.emailEnabled());
            row.put("include_in_total", true);
            row.put("row_type", "group");
            rows.add(row);

            List<Category> sortedSubs = new ArrayList<>(subs);
            sortedSubs.sort(categoryOrder());
            for (Category cat : sortedSubs) {
                Budget sb = catBudgets.get(cat.id);
                BigDecimal subForecast = sb != null ? Dec.orZero(sb.forecast) : Dec.ZERO;
                BigDecimal subAct = Dec.orZero(actuals.get(cat.id));
                if (subForecast.signum() <= 0 && subAct.signum() <= 0) {
                    continue;
                }
                CategoryGroup parent = groupsMap.get(cat.groupId);
                BigDecimal subUtil = utilizationPct(subAct, subForecast);
                Threshold st = thresholdFor.apply(cat.id);
                Map<String, Object> sub = new LinkedHashMap<>();
                sub.put("category_id", cat.id);
                sub.put("category_name", cat.name);
                sub.put("group_name", parent == null ? "" : parent.name);
                sub.put("forecast", subForecast);
                sub.put("actual", subAct);
                sub.put("remaining", subForecast.subtract(subAct));
                sub.put("variance", variance(subAct, subForecast));
                sub.put("utilization_pct", subUtil);
                sub.put("status", utilizationStatus(subUtil, st.warnPct(), st.criticalPct()));
                sub.put("warn_pct", st.warnPct());
                sub.put("critical_pct", st.criticalPct());
                sub.put("email_enabled", st.emailEnabled());
                sub.put("include_in_total", false);
                sub.put("row_type", "subcategory");
                sub.put("parent_group_id", g.id);
                rows.add(sub);
            }
        }

        BigDecimal unmapped = Dec.orZero(actuals.get(UNMAPPED_CATEGORY_ID));
        if (unmapped.signum() > 0) {
            Map<String, Object> row = new LinkedHashMap<>();
            row.put("category_id", UNMAPPED_CATEGORY_ID);
            row.put("category_name", "Unmapped expenses");
            row.put("group_name", "Other");
            row.put("forecast", Dec.ZERO);
            row.put("actual", unmapped);
            row.put("remaining", unmapped.negate());
            row.put("variance", unmapped);
            row.put("utilization_pct", null);
            row.put("status", "warn");
            row.put("warn_pct", DEFAULT_WARN_PCT);
            row.put("critical_pct", DEFAULT_CRITICAL_PCT);
            row.put("email_enabled", true);
            row.put("include_in_total", true);
            row.put("row_type", "unmapped");
            rows.add(row);
        }

        BigDecimal totalForecast = Dec.ZERO;
        BigDecimal totalActual = Dec.ZERO;
        for (Map<String, Object> r : rows) {
            if (Boolean.TRUE.equals(r.getOrDefault("include_in_total", true))) {
                totalForecast = totalForecast.add((BigDecimal) r.get("forecast"));
                totalActual = totalActual.add((BigDecimal) r.get("actual"));
            }
        }
        BigDecimal overallUtil = utilizationPct(totalActual, totalForecast);
        Threshold global = thresholdFor.apply(null);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("report_currency", reportCurrency == null || reportCurrency.isEmpty() ? "USD" : reportCurrency);
        out.put("rows", rows);
        out.put("total_forecast", totalForecast);
        out.put("total_actual", totalActual);
        out.put("overall_variance", variance(totalActual, totalForecast));
        out.put("overall_util", overallUtil);
        out.put("overall_status", utilizationStatus(overallUtil, global.warnPct(), global.criticalPct()));
        out.put("remaining", totalForecast.subtract(totalActual));
        return out;
    }

    /**
     * suggest_category_for_description: longest keyword contained in the description; the user's
     * links win over global ones.
     */
    public Optional<Category> suggestCategory(String description, String userId) {
        if (description == null || description.isEmpty()) {
            return Optional.empty();
        }
        String descLower = description.toLowerCase(Locale.ROOT);
        if (userId != null) {
            Optional<Category> cat = bestFrom(merchantLinks.findByUserIdOrderByIdAsc(userId), descLower);
            if (cat.isPresent()) {
                return cat;
            }
        }
        List<MerchantLink> global = merchantLinks.findAllByOrderByIdAsc().stream()
                .filter(l -> l.userId == null || l.userId.isEmpty()).toList();
        return bestFrom(global, descLower);
    }

    private Optional<Category> bestFrom(List<MerchantLink> links, String descLower) {
        MerchantLink best = null;
        int bestLen = 0;
        for (MerchantLink link : links) {
            String kw = link.keyword == null ? "" : link.keyword.strip().toLowerCase(Locale.ROOT);
            if (kw.isEmpty()) {
                continue;
            }
            if (descLower.contains(kw) && kw.length() > bestLen) {
                best = link;
                bestLen = kw.length();
            }
        }
        return best == null ? Optional.empty() : categories.get(best.categoryId);
    }

    /** Normalised merchant label for grouping unmatched imported rows. */
    public static String merchantKey(String description) {
        if (description == null || description.isEmpty()) {
            return "";
        }
        String text = String.join(" ", description.strip().split("\\s+")).strip();
        return text.length() > 120 ? text.substring(0, 120) : text;
    }

    /** Set the subcategory and keep the original bank description in the note. */
    private void assignMerchantCategory(Transaction t, String categoryId) {
        String merchantName = categories.get(categoryId).map(c -> c.name).orElse("").strip();
        String original = t.description == null ? "" : t.description.strip();
        if (!original.isEmpty() && !merchantName.isEmpty() && !original.equalsIgnoreCase(merchantName)) {
            String existing = t.note == null ? "" : t.note.strip();
            if (existing.isEmpty()) {
                t.note = original;
            } else if (!existing.contains(original)) {
                t.note = original + " · " + existing;
            }
            t.description = merchantName.length() > 500 ? merchantName.substring(0, 500) : merchantName;
        }
        t.categoryId = categoryId;
    }

    /** Categorise matching (or explicitly listed) expense transactions; returns how many changed. */
    public int applyMerchantLink(String userId, String keyword, String categoryId, List<String> transactionIds) {
        String kw = keyword == null ? "" : keyword.strip().toLowerCase(Locale.ROOT);
        if (kw.isEmpty() && (transactionIds == null || transactionIds.isEmpty())) {
            return 0;
        }
        Set<String> idSet = transactionIds == null ? Set.of() : new LinkedHashSet<>(transactionIds);
        List<Transaction> candidates = new ArrayList<>();
        if (!idSet.isEmpty()) {
            for (String tid : idSet) {
                transactions.get(tid).filter(t -> userId.equals(t.userId)).ifPresent(candidates::add);
            }
        } else {
            candidates = transactions.listByUser(userId, null, 500);
        }
        int updated = 0;
        Set<String> done = new HashSet<>();
        for (Transaction t : candidates) {
            if (!"expense".equals(t.direction) || !done.add(t.id)) {
                continue;
            }
            String desc = t.description == null ? "" : t.description.toLowerCase(Locale.ROOT);
            if (!idSet.isEmpty() && idSet.contains(t.id)) {
                assignMerchantCategory(t, categoryId);
                transactions.save(t);
                updated++;
                continue;
            }
            if (!kw.isEmpty() && desc.contains(kw) && (t.categoryId == null || t.categoryId.isEmpty())) {
                assignMerchantCategory(t, categoryId);
                transactions.save(t);
                updated++;
            }
        }
        return updated;
    }

    public BigDecimal remainingPrincipal(Commitment c) {
        return scheduleLines.sumOutstandingByCommitment(c.id);
    }
}
