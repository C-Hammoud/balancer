package com.financetracker.finance.web;

import static com.financetracker.finance.web.FinanceJson.dec;
import static com.financetracker.finance.web.FinanceJson.queryInt;
import static com.financetracker.finance.web.FinanceJson.uid;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.time.format.TextStyle;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.financetracker.access.api.UserDirectory;
import com.financetracker.finance.application.AlertService;
import com.financetracker.finance.application.ReportService;
import com.financetracker.finance.domain.BudgetAlert;
import com.financetracker.finance.domain.FinanceRepositories.BudgetAlertRepository;

/** Dashboard, yearly overview and utilization report. */
@RestController
@RequestMapping("/api/v1/budgeting")
class ReportsController {

    private final ReportService reports;
    private final AlertService alerts;
    private final BudgetAlertRepository alertRepository;
    private final UserDirectory users;
    private final Clock clock;

    ReportsController(ReportService reports, AlertService alerts, BudgetAlertRepository alertRepository,
            UserDirectory users, Clock clock) {
        this.reports = reports;
        this.alerts = alerts;
        this.alertRepository = alertRepository;
        this.users = users;
        this.clock = clock;
    }

    @GetMapping("/dashboard/")
    Map<String, Object> dashboard(@RequestParam(required = false) String year, @RequestParam(required = false) String month,
            @RequestParam(name = "report_currency", required = false) String reportCurrency) {
        String uid = uid();
        LocalDate today = LocalDate.now(clock);
        int y = queryInt(year, today.getYear());
        int m = queryInt(month, today.getMonthValue());
        alerts.refresh(uid, y, m, false);
        String currency = users.reportCurrency(uid, reportCurrency);
        Map<String, Object> report = reports.utilizationReport(uid, y, m, currency);
        Instant now = Instant.now(clock);
        List<Map<String, Object>> open = alertRepository.listByUser(uid, true, 200).stream()
                .filter(a -> a.year == y && a.month == m && !a.isSnoozed(now))
                .map(ReportsController::openAlert)
                .toList();
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("year", y);
        out.put("month", m);
        out.put("report_currency", currency);
        out.put("report", report);
        out.put("income_total", reports.actualIncomeTotal(uid, y, m, currency));
        out.put("expense_total", reports.actualExpenseTotal(uid, y, m, currency));
        out.put("open_alerts", open);
        return dec(out);
    }

    private static Map<String, Object> openAlert(BudgetAlert a) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", a.id);
        m.put("severity", a.severity);
        m.put("title", a.title);
        m.put("description", a.description);
        m.put("alert_type", a.alertType == null || a.alertType.isEmpty() ? "utilization" : a.alertType);
        m.put("category_id", a.categoryId);
        m.put("utilization_pct", a.utilizationPct);
        m.put("is_resolved", a.isResolved);
        return m;
    }

    @GetMapping("/yearly/")
    @SuppressWarnings("unchecked")
    Map<String, Object> yearly(@RequestParam(required = false) String year,
            @RequestParam(name = "report_currency", required = false) String reportCurrency) {
        String uid = uid();
        int y = queryInt(year, LocalDate.now(clock).getYear());
        String currency = users.reportCurrency(uid, reportCurrency);
        Map<String, Object> payload = reports.yearlyOverview(uid, y, currency);
        for (Map<String, Object> row : (List<Map<String, Object>>) payload.get("months")) {
            int m = (int) row.get("month");
            String name = java.time.Month.of(m).getDisplayName(TextStyle.FULL, Locale.ENGLISH);
            row.put("month_name", name);
            row.put("month_short", name.substring(0, 3));
        }
        return dec(payload);
    }

    @GetMapping("/utilization/")
    Map<String, Object> utilization(@RequestParam(required = false) String year, @RequestParam(required = false) String month,
            @RequestParam(name = "report_currency", required = false) String reportCurrency) {
        String uid = uid();
        LocalDate today = LocalDate.now(clock);
        String currency = users.reportCurrency(uid, reportCurrency);
        return dec(reports.utilizationReport(uid, queryInt(year, today.getYear()), queryInt(month, today.getMonthValue()), currency));
    }
}
