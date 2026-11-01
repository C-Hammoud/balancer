package com.financetracker.finance.web;

import static com.financetracker.finance.web.FinanceJson.dec;
import static com.financetracker.finance.web.FinanceJson.queryInt;
import static com.financetracker.finance.web.FinanceJson.uid;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.financetracker.access.api.UserDirectory;
import com.financetracker.finance.application.AlertService;
import com.financetracker.finance.application.CategoryAccess;
import com.financetracker.finance.application.Dec;
import com.financetracker.finance.application.ReportService;
import com.financetracker.finance.domain.Budget;
import com.financetracker.finance.domain.Category;
import com.financetracker.finance.domain.CategoryGroup;
import com.financetracker.finance.domain.FinanceRepositories.BudgetRepository;
import com.financetracker.finance.domain.FinanceRepositories.SavingsRepository;
import com.financetracker.finance.domain.Savings;
import com.financetracker.shared.error.ApiException;
import com.financetracker.shared.web.Field;
import com.financetracker.shared.web.RequestData;

/** Monthly forecasts (per group or subcategory) and savings. */
@RestController
@RequestMapping("/api/v1/budgeting")
class BudgetsController {

    private static final Map<String, String> GOAL_LABELS = Map.of("met", "Met", "missed", "Missed", "pending", "Pending");

    private final BudgetRepository budgets;
    private final SavingsRepository savings;
    private final CategoryAccess categoryAccess;
    private final ReportService reports;
    private final AlertService alerts;
    private final UserDirectory users;
    private final Clock clock;

    BudgetsController(BudgetRepository budgets, SavingsRepository savings, CategoryAccess categoryAccess,
            ReportService reports, AlertService alerts, UserDirectory users, Clock clock) {
        this.budgets = budgets;
        this.savings = savings;
        this.categoryAccess = categoryAccess;
        this.reports = reports;
        this.alerts = alerts;
        this.users = users;
        this.clock = clock;
    }

    @GetMapping("/budgets/")
    Map<String, Object> list(@RequestParam(required = false) String year, @RequestParam(required = false) String month) {
        String uid = uid();
        LocalDate today = LocalDate.now(clock);
        int y = queryInt(year, today.getYear());
        int m = queryInt(month, today.getMonthValue());
        CategoryAccess.Visible visible = categoryAccess.forUser(uid);
        List<Budget> monthBudgets = budgets.listByUser(uid, y, m);
        Map<String, BigDecimal> actuals = reports.actualExpenseByCategory(uid, y, m, false, null);
        Map<String, Budget> groupBudgets = new LinkedHashMap<>();
        Map<String, Budget> catBudgets = new LinkedHashMap<>();
        for (Budget b : monthBudgets) {
            boolean hasCat = b.categoryId != null && !b.categoryId.strip().isEmpty();
            if (hasCat) {
                catBudgets.put(b.categoryId, b);
            } else if (b.groupId != null && !b.groupId.strip().isEmpty()) {
                groupBudgets.put(b.groupId, b);
            }
        }
        List<CategoryGroup> groups = new ArrayList<>(visible.groups());
        groups.sort(Comparator.comparingInt((CategoryGroup g) -> g.order).thenComparing(g -> g.name.toLowerCase(Locale.ROOT)));
        List<Map<String, Object>> rows = new ArrayList<>();
        for (CategoryGroup g : groups) {
            List<Category> subs = new ArrayList<>(visible.categoriesById().values().stream()
                    .filter(c -> g.id.equals(c.groupId) && c.includeInReports).toList());
            if (subs.isEmpty()) {
                continue;
            }
            subs.sort(Comparator.comparingInt((Category c) -> c.order).thenComparing(c -> c.name.toLowerCase(Locale.ROOT)));
            BigDecimal groupActual = Dec.ZERO;
            List<Map<String, Object>> subBudgets = new ArrayList<>();
            for (Category cat : subs) {
                BigDecimal act = Dec.orZero(actuals.get(cat.id));
                groupActual = groupActual.add(act);
                Budget sb = catBudgets.get(cat.id);
                Map<String, Object> sub = new LinkedHashMap<>();
                sub.put("category_id", cat.id);
                sub.put("category_name", cat.name);
                sub.put("forecast", sb != null ? sb.forecast : Dec.ZERO);
                sub.put("actual", act);
                subBudgets.add(sub);
            }
            BigDecimal subSum = ReportService.subForecastSum(catBudgets, subs);
            Budget gb = groupBudgets.get(g.id);
            BigDecimal effective = ReportService.effectiveGroupForecast(gb, subSum);
            BigDecimal explicit = gb != null && Dec.pos(gb.forecast) ? gb.forecast : null;
            if (gb != null || !subBudgets.isEmpty() || groupActual.signum() > 0 || subSum.signum() > 0) {
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("group_id", g.id);
                row.put("category_id", null);
                row.put("category_name", g.name);
                row.put("forecast", effective);
                row.put("forecast_explicit", explicit);
                row.put("forecast_from_subs", subSum);
                row.put("forecast_is_derived", explicit == null && subSum.signum() > 0);
                row.put("actual", groupActual);
                row.put("sub_budgets", subBudgets);
                rows.add(row);
            }
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("year", y);
        out.put("month", m);
        out.put("rows", rows);
        return dec(out);
    }

    private static BigDecimal forecast(Map<String, Object> body) {
        RequestData d = RequestData.of(body);
        BigDecimal f = d.decimal("forecast", Field.required().digits(12, 2));
        d.validate();
        return f;
    }

    @PatchMapping("/budgets/{year:\\d+}/{month:\\d+}/group/{groupId}/")
    Map<String, Object> patchGroup(@PathVariable int year, @PathVariable int month, @PathVariable String groupId,
            @RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        if (categoryAccess.visibleGroup(uid, groupId).isEmpty()) {
            throw ApiException.notFound("Category not found.");
        }
        Budget b = budgets.getByUserGroupMonth(uid, groupId, year, month).orElseGet(() -> newBudget(uid, "", groupId, year, month));
        b.forecast = forecast(body);
        budgets.save(b);
        alerts.trigger(uid, year, month);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("forecast", b.forecast);
        out.put("group_id", groupId);
        out.put("year", year);
        out.put("month", month);
        return dec(out);
    }

    private static Budget newBudget(String uid, String categoryId, String groupId, int year, int month) {
        Budget b = new Budget();
        b.userId = uid;
        b.categoryId = categoryId;
        b.groupId = groupId;
        b.year = year;
        b.month = month;
        b.forecast = Dec.ZERO;
        return b;
    }

    /** GET creates the (zero) budget row when it does not exist yet, as the Django view did. */
    @GetMapping("/budgets/{year:\\d+}/{month:\\d+}/{categoryId}/")
    Map<String, Object> getCategory(@PathVariable int year, @PathVariable int month, @PathVariable String categoryId) {
        String uid = uid();
        Budget b = budgets.getByUserCategoryMonth(uid, categoryId, year, month).orElseGet(() -> {
            Budget nb = newBudget(uid, categoryId, "", year, month);
            budgets.save(nb);
            return nb;
        });
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("forecast", b.forecast);
        out.put("category_id", categoryId);
        out.put("year", year);
        out.put("month", month);
        return dec(out);
    }

    @PatchMapping("/budgets/{year:\\d+}/{month:\\d+}/{categoryId}/")
    Map<String, Object> patchCategory(@PathVariable int year, @PathVariable int month, @PathVariable String categoryId,
            @RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        if (categoryAccess.visibleCategory(uid, categoryId).isEmpty()) {
            throw ApiException.notFound("Category not found.");
        }
        Budget b = budgets.getByUserCategoryMonth(uid, categoryId, year, month)
                .orElseGet(() -> newBudget(uid, categoryId, "", year, month));
        b.forecast = forecast(body);
        budgets.save(b);
        alerts.trigger(uid, year, month);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("forecast", b.forecast);
        return dec(out);
    }

    // ---------------------------------------------------------------- savings

    @GetMapping("/savings/")
    List<Map<String, Object>> savingsList(@RequestParam(name = "report_currency", required = false) String reportCurrency) {
        String uid = uid();
        String currency = users.reportCurrency(uid, reportCurrency);
        List<Map<String, Object>> out = new ArrayList<>();
        for (Savings s : savings.listByUser(uid)) {
            BigDecimal actual = s.actual != null ? s.actual : reports.savingsActual(uid, s.year, s.month, currency);
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("year", s.year);
            m.put("month", s.month);
            m.put("report_currency", currency);
            m.put("target", s.target);
            m.put("actual", actual);
            m.put("goal_status", s.goalStatus);
            m.put("goal_status_display", GOAL_LABELS.getOrDefault(s.goalStatus, s.goalStatus));
            out.add(dec(m));
        }
        return out;
    }

    @GetMapping("/savings/{year:\\d+}/{month:\\d+}/")
    Map<String, Object> savingsDetail(@PathVariable int year, @PathVariable int month,
            @RequestParam(name = "report_currency", required = false) String reportCurrency) {
        String uid = uid();
        Savings s = savings.getByUserMonth(uid, year, month).orElseThrow(ApiException::notFound);
        String currency = users.reportCurrency(uid, reportCurrency);
        BigDecimal actual = s.actual != null ? s.actual : reports.savingsActual(uid, s.year, s.month, currency);
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("year", s.year);
        m.put("month", s.month);
        m.put("target", s.target);
        m.put("actual", actual);
        m.put("report_currency", currency);
        m.put("goal_status", s.goalStatus);
        return dec(m);
    }

    @PatchMapping("/savings/{year:\\d+}/{month:\\d+}/")
    Map<String, Object> savingsUpdate(@PathVariable int year, @PathVariable int month,
            @RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        Savings s = savings.getByUserMonth(uid, year, month).orElseGet(() -> {
            Savings ns = new Savings();
            ns.userId = uid;
            ns.year = year;
            ns.month = month;
            ns.target = Dec.ZERO;
            ns.goalStatus = "pending";
            return ns;
        });
        Map<String, Object> data = new LinkedHashMap<>(body == null ? Map.of() : body);
        data.put("year", year);
        data.put("month", month);
        RequestData d = RequestData.of(data);
        d.integer("year", Field.required());
        d.integer("month", Field.required().min(1).max(12));
        BigDecimal target = d.decimal("target", Field.required().digits(12, 2));
        BigDecimal actual = d.decimal("actual", Field.optional().allowNull().digits(12, 2));
        String goal = d.choice("goal_status", List.of("met", "missed", "pending"), Field.required());
        d.validate();
        s.target = target;
        s.actual = actual;
        s.goalStatus = goal;
        savings.save(s);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("target", s.target);
        out.put("actual", s.actual);
        out.put("goal_status", s.goalStatus);
        return dec(out);
    }
}
