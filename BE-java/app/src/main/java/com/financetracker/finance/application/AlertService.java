package com.financetracker.finance.application;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.financetracker.access.api.UserDirectory;
import com.financetracker.access.api.UserSummary;
import com.financetracker.finance.domain.BudgetAlert;
import com.financetracker.finance.domain.Commitment;
import com.financetracker.finance.domain.FinanceRepositories.BudgetAlertRepository;
import com.financetracker.finance.domain.FinanceRepositories.CommitmentRepository;
import com.financetracker.finance.domain.ScheduleLine;
import com.financetracker.notifications.api.TransactionalEmails;
import com.financetracker.shared.web.Py;

/** Port of budgeting/alerts.py: utilization and commitment due-date alerts. */
@Service
public class AlertService {

    private static final Logger log = LoggerFactory.getLogger(AlertService.class);
    static final long BUDGET_ALERT_TTL_NANOS = Duration.ofSeconds(300).toNanos();
    static final long COMMITMENT_ALERT_TTL_NANOS = Duration.ofSeconds(300).toNanos();
    public static final List<Integer> SNOOZE_DAY_CHOICES = List.of(1, 3, 7);

    /** In-process throttle so GET /alerts/ does not re-run the evaluation every time. */
    private final Map<String, Long> evalCache = new ConcurrentHashMap<>();

    private final BudgetAlertRepository alerts;
    private final CommitmentRepository commitments;
    private final ReportService reports;
    private final CommitmentScheduleService schedules;
    private final UserDirectory users;
    private final TransactionalEmails emails;
    private final Clock clock;

    public AlertService(BudgetAlertRepository alerts, CommitmentRepository commitments, ReportService reports,
            CommitmentScheduleService schedules, UserDirectory users, TransactionalEmails emails, Clock clock) {
        this.alerts = alerts;
        this.commitments = commitments;
        this.reports = reports;
        this.schedules = schedules;
        this.users = users;
        this.emails = emails;
        this.clock = clock;
    }

    public void invalidateCache(String userId) {
        evalCache.keySet().removeIf(k -> k.startsWith(userId + ":"));
    }

    /** Re-evaluate utilization and due alerts (throttled unless force). */
    public void refresh(String userId, Integer year, Integer month, boolean force) {
        LocalDate today = LocalDate.now(clock);
        int y = year != null ? year : today.getYear();
        int m = month != null ? month : today.getMonthValue();
        String budgetKey = userId + ":budget:" + y + ":" + m;
        String commitmentKey = userId + ":commitment";
        long now = System.nanoTime();
        boolean runBudget = force || now - evalCache.getOrDefault(budgetKey, Long.MIN_VALUE / 2) >= BUDGET_ALERT_TTL_NANOS;
        boolean runCommitment = force
                || now - evalCache.getOrDefault(commitmentKey, Long.MIN_VALUE / 2) >= COMMITMENT_ALERT_TTL_NANOS;
        if (runBudget) {
            evaluateBudgetAlerts(userId, y, m);
            evalCache.put(budgetKey, System.nanoTime());
        }
        if (runCommitment) {
            evaluateCommitmentDueAlerts(userId);
            evalCache.put(commitmentKey, System.nanoTime());
        }
    }

    /** api.utils.trigger_budget_alerts: forced refresh after data changes; failures are ignored. */
    public void trigger(String userId, Integer year, Integer month) {
        try {
            refresh(userId, year, month, true);
        } catch (RuntimeException e) {
            log.debug("Alert refresh failed for user {}: {}", userId, e.getMessage());
        }
    }

    private static Map<String, Object> openStateFields(BudgetAlert a) {
        if (a.isResolved && BudgetAlert.RESOLUTION_USER.equals(a.resolution)) {
            return Map.of();
        }
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("is_resolved", false);
        m.put("resolution", "");
        m.put("resolved_at", null);
        return m;
    }

    private void autoResolve(BudgetAlert a) {
        a.isResolved = true;
        a.resolution = BudgetAlert.RESOLUTION_AUTO;
        a.resolvedAt = Instant.now(clock);
        alerts.save(a);
    }

    private boolean shouldEmail(BudgetAlert a) {
        return !a.emailSent && !a.isResolved && !a.isSnoozed(Instant.now(clock));
    }

    private static boolean decEq(BigDecimal a, BigDecimal b) {
        if (a == null || b == null) {
            return a == b;
        }
        return a.compareTo(b) == 0;
    }

    /** _save_alert_if_changed for the fields both evaluations set. */
    private boolean saveIfChanged(BudgetAlert a, String title, String description, String severity, Integer year,
            Integer month, String categoryId, String alertType, BigDecimal utilizationPct, BigDecimal actual,
            BigDecimal forecast, String commitmentId, String scheduleLineId, String dueDate, String commitmentName,
            Map<String, Object> openState) {
        boolean changed = false;
        if (!Objects.equals(a.title, title)) { a.title = title; changed = true; }
        if (!Objects.equals(a.description, description)) { a.description = description; changed = true; }
        if (severity != null && !Objects.equals(a.severity, severity)) { a.severity = severity; changed = true; }
        if (year != null && a.year != year) { a.year = year; changed = true; }
        if (month != null && a.month != month) { a.month = month; changed = true; }
        if (categoryId != null && !Objects.equals(a.categoryId, categoryId)) { a.categoryId = categoryId; changed = true; }
        if (!Objects.equals(a.alertType, alertType)) { a.alertType = alertType; changed = true; }
        if (!decEq(a.utilizationPct, utilizationPct)) { a.utilizationPct = utilizationPct; changed = true; }
        if (!decEq(a.actual, actual)) { a.actual = actual; changed = true; }
        if (!decEq(a.forecast, forecast)) { a.forecast = forecast; changed = true; }
        if (commitmentId != null && !Objects.equals(a.commitmentId, commitmentId)) { a.commitmentId = commitmentId; changed = true; }
        if (scheduleLineId != null && !Objects.equals(a.scheduleLineId, scheduleLineId)) { a.scheduleLineId = scheduleLineId; changed = true; }
        if (dueDate != null && !Objects.equals(a.dueDate, dueDate)) { a.dueDate = dueDate; changed = true; }
        if (commitmentName != null && !Objects.equals(a.commitmentName, commitmentName)) { a.commitmentName = commitmentName; changed = true; }
        if (!openState.isEmpty()) {
            if (a.isResolved) { a.isResolved = false; changed = true; }
            if (!"".equals(a.resolution)) { a.resolution = ""; changed = true; }
            if (a.resolvedAt != null) { a.resolvedAt = null; changed = true; }
        }
        if (changed) {
            alerts.save(a);
        }
        return changed;
    }

    private record Desired(String categoryId, String severity, BigDecimal utilizationPct, BigDecimal actual,
            BigDecimal forecast, String categoryName, boolean emailEnabled) {
    }

    /**
     * Compare the utilization report to thresholds: create/update open alerts, resolve those back
     * under threshold, email once per fingerprint. Returns the open utilization alerts.
     */
    @SuppressWarnings("unchecked")
    public List<BudgetAlert> evaluateBudgetAlerts(String userId, int year, int month) {
        Map<String, Object> report;
        try {
            report = reports.utilizationReport(userId, year, month, null);
        } catch (RuntimeException e) {
            log.warn("budget_utilization_report failed: {}", e.getMessage());
            return List.of();
        }
        Map<String, Desired> desired = new LinkedHashMap<>();
        for (Map<String, Object> row : (List<Map<String, Object>>) report.get("rows")) {
            String catId = String.valueOf(row.get("category_id"));
            if (catId.startsWith("commitment:")) {
                continue;
            }
            BigDecimal util = (BigDecimal) row.get("utilization_pct");
            String status = row.get("status") == null ? "ok" : (String) row.get("status");
            if (!List.of("warn", "critical", "over").contains(status)) {
                continue;
            }
            String severity = "warn".equals(status) ? "WARN" : "CRITICAL";
            List<String> severities = List.of(severity);
            BigDecimal warnPct = row.get("warn_pct") instanceof BigDecimal w ? w : new BigDecimal("80");
            if ("CRITICAL".equals(severity) && util != null && util.compareTo(warnPct) >= 0) {
                severities = List.of("WARN", "CRITICAL");
            }
            String name = row.get("category_name") == null || String.valueOf(row.get("category_name")).isEmpty()
                    ? catId : String.valueOf(row.get("category_name"));
            boolean emailEnabled = !Boolean.FALSE.equals(row.getOrDefault("email_enabled", true));
            for (String sev : severities) {
                desired.put(BudgetAlert.fingerprint(userId, year, month, catId, sev),
                        new Desired(catId, sev, util, (BigDecimal) row.get("actual"), (BigDecimal) row.get("forecast"),
                                name, emailEnabled));
            }
        }

        List<BudgetAlert> open = new ArrayList<>();
        List<BudgetAlert> existingMonth = alerts.listByUser(userId, false, 500).stream()
                .filter(a -> a.year == year && a.month == month && isUtilization(a)).toList();
        Map<String, BudgetAlert> byFp = new LinkedHashMap<>();
        for (BudgetAlert a : existingMonth) {
            if (a.fingerprint != null && !a.fingerprint.isEmpty()) {
                byFp.put(a.fingerprint, a);
            }
        }
        String period = year + "-" + String.format("%02d", month);
        for (Map.Entry<String, Desired> e : desired.entrySet()) {
            Desired meta = e.getValue();
            String title;
            String description;
            if (ReportService.UNMAPPED_CATEGORY_ID.equals(meta.categoryId())) {
                title = meta.severity() + ": Unmapped expenses";
                description = "You have " + Py.dec(meta.actual()) + " in expenses without a category mapping for "
                        + period + ". Open type maps to assign expense types to budget categories.";
            } else {
                title = meta.severity() + ": " + meta.categoryName() + " budget";
                String utilStr = meta.utilizationPct() != null ? Py.dec(meta.utilizationPct()) + "%" : "n/a";
                description = meta.categoryName() + " utilization is " + utilStr + " (actual " + Py.dec(meta.actual())
                        + ", forecast " + Py.dec(meta.forecast()) + ") for " + period + ".";
            }
            BudgetAlert alert = byFp.get(e.getKey());
            if (alert != null) {
                saveIfChanged(alert, title, description, null, null, null, null, "utilization", meta.utilizationPct(),
                        meta.actual(), meta.forecast(), null, null, null, null, openStateFields(alert));
            } else {
                alert = new BudgetAlert();
                alert.userId = userId;
                alert.year = year;
                alert.month = month;
                alert.categoryId = meta.categoryId();
                alert.severity = meta.severity();
                alert.title = title;
                alert.description = description;
                alert.alertType = "utilization";
                alert.utilizationPct = meta.utilizationPct();
                alert.actual = meta.actual();
                alert.forecast = meta.forecast();
                alert.fingerprint = e.getKey();
                alerts.save(alert);
                byFp.put(e.getKey(), alert);
            }
            if (meta.emailEnabled() && shouldEmail(alert) && sendAlertEmail(userId, alert)) {
                alert.emailSent = true;
                alerts.save(alert);
            }
            if (!alert.isResolved) {
                open.add(alert);
            }
        }
        for (BudgetAlert a : existingMonth) {
            if (a.fingerprint != null && !a.fingerprint.isEmpty() && !desired.containsKey(a.fingerprint) && !a.isResolved) {
                autoResolve(a);
            }
        }
        return open;
    }

    private record DueMeta(int year, int month, String categoryId, String severity, String title, String description,
            BigDecimal actual, String commitmentId, String scheduleLineId, String dueDate, String commitmentName) {
    }

    /** In-app alerts for installments due within the reminder window, or overdue. */
    public List<BudgetAlert> evaluateCommitmentDueAlerts(String userId) {
        LocalDate today = LocalDate.now(clock);
        Map<String, DueMeta> desired = new LinkedHashMap<>();
        for (Commitment c : commitments.listByUser(userId)) {
            int daysBefore = c.reminderDaysBefore == 0 ? 3 : c.reminderDaysBefore;
            for (ScheduleLine line : schedules.ensure(c)) {
                if (!ScheduleLine.OUTSTANDING.equals(line.status) || line.dueDate == null) {
                    continue;
                }
                LocalDate due = line.dueDate;
                boolean overdue = due.isBefore(today);
                LocalDate windowStart = due.minusDays(daysBefore);
                boolean upcoming = !today.isBefore(windowStart) && !today.isAfter(due);
                if (!overdue && !upcoming) {
                    continue;
                }
                String severity = overdue ? "CRITICAL" : "WARN";
                String fp = userId + "|due|" + line.id + "|" + severity;
                String dueStr = due.toString();
                String amt = Py.dec(line.amount);
                String title = overdue ? "Overdue: " + c.name : "Due soon: " + c.name;
                String description = overdue
                        ? "Commitment “" + c.name + "” payment of " + amt + " was due on " + dueStr
                                + " and is still outstanding."
                        : "Commitment “" + c.name + "” payment of " + amt + " is due on " + dueStr + ".";
                desired.put(fp, new DueMeta(due.getYear(), due.getMonthValue(), "commitment:" + c.id, severity, title,
                        description, line.amount, c.id, line.id, dueStr, c.name));
            }
        }
        List<BudgetAlert> existingDue = alerts.listByUser(userId, false, 500).stream().filter(AlertService::isCommitmentDue).toList();
        Map<String, BudgetAlert> byFp = new LinkedHashMap<>();
        for (BudgetAlert a : existingDue) {
            if (a.fingerprint != null && !a.fingerprint.isEmpty()) {
                byFp.put(a.fingerprint, a);
            }
        }
        List<BudgetAlert> open = new ArrayList<>();
        for (Map.Entry<String, DueMeta> e : desired.entrySet()) {
            DueMeta meta = e.getValue();
            BudgetAlert alert = byFp.get(e.getKey());
            if (alert != null) {
                saveIfChanged(alert, meta.title(), meta.description(), meta.severity(), meta.year(), meta.month(),
                        meta.categoryId(), "commitment_due", null, meta.actual(), Dec.ZERO, meta.commitmentId(),
                        meta.scheduleLineId(), meta.dueDate(), meta.commitmentName(), openStateFields(alert));
            } else {
                alert = new BudgetAlert();
                alert.userId = userId;
                alert.year = meta.year();
                alert.month = meta.month();
                alert.categoryId = meta.categoryId();
                alert.severity = meta.severity();
                alert.title = meta.title();
                alert.description = meta.description();
                alert.alertType = "commitment_due";
                alert.utilizationPct = null;
                alert.actual = meta.actual();
                alert.forecast = Dec.ZERO;
                alert.commitmentId = meta.commitmentId();
                alert.scheduleLineId = meta.scheduleLineId();
                alert.dueDate = meta.dueDate();
                alert.commitmentName = meta.commitmentName();
                alert.fingerprint = e.getKey();
                alerts.save(alert);
                byFp.put(e.getKey(), alert);
            }
            if (!alert.isResolved) {
                open.add(alert);
            }
            if (shouldEmail(alert) && sendAlertEmail(userId, alert)) {
                alert.emailSent = true;
                alerts.save(alert);
            }
        }
        for (BudgetAlert a : existingDue) {
            if (a.fingerprint != null && !a.fingerprint.isEmpty() && !desired.containsKey(a.fingerprint) && !a.isResolved) {
                autoResolve(a);
            }
        }
        return open;
    }

    static boolean isCommitmentDue(BudgetAlert a) {
        if ("commitment_due".equals(a.alertType)) {
            return true;
        }
        if (a.fingerprint != null && a.fingerprint.contains("|due|")) {
            return true;
        }
        return a.categoryId != null && a.categoryId.startsWith("commitment:");
    }

    /**
     * Classify by type: other alert kinds (commitment due dates, risk) must never be auto-resolved
     * by the utilization evaluator. Old rows without a type are utilization alerts.
     */
    static boolean isUtilization(BudgetAlert a) {
        String type = a.alertType == null || a.alertType.isEmpty() ? "utilization" : a.alertType;
        boolean risk = "risk".equals(type) || (a.categoryId != null && a.categoryId.startsWith("risk:"));
        return "utilization".equals(type) && !isCommitmentDue(a) && !risk;
    }

    private boolean sendAlertEmail(String userId, BudgetAlert alert) {
        Optional<UserSummary> user = users.findById(userId);
        if (user.isEmpty() || user.get().email() == null || user.get().email().strip().isEmpty()) {
            log.info("No email for user {}; skipping alert mail fingerprint={}", userId, alert.fingerprint);
            return false;
        }
        try {
            return emails.budgetAlert(CommitmentScheduleService.recipient(user.get()), alert.title,
                    alert.description == null ? "" : alert.description,
                    alert.severity == null || alert.severity.isEmpty() ? "info" : alert.severity);
        } catch (RuntimeException e) {
            log.warn("Failed to send budget alert email: {}", e.getMessage());
            return false;
        }
    }

    /** Email open alerts that were not emailed yet. Returns how many were sent. */
    public int sendPendingEmails(String userId) {
        int sent = 0;
        for (BudgetAlert a : alerts.listByUser(userId, true, 500)) {
            if (!shouldEmail(a)) {
                continue;
            }
            if (sendAlertEmail(userId, a)) {
                a.emailSent = true;
                alerts.save(a);
                sent++;
            }
        }
        return sent;
    }

    /** process_budget_alerts: re-evaluate and email for the given users (all active users when empty). */
    public Map<String, Integer> process(List<String> userIds) {
        LocalDate today = LocalDate.now(clock);
        List<String> ids = userIds != null ? userIds
                : users.findAll().stream().filter(UserSummary::active).map(UserSummary::userId).toList();
        Map<String, Integer> stats = new LinkedHashMap<>();
        stats.put("users", 0);
        stats.put("emails_sent", 0);
        stats.put("errors", 0);
        for (String uid : ids) {
            stats.merge("users", 1, Integer::sum);
            try {
                refresh(uid, today.getYear(), today.getMonthValue(), true);
                stats.merge("emails_sent", sendPendingEmails(uid), Integer::sum);
            } catch (RuntimeException e) {
                stats.merge("errors", 1, Integer::sum);
                log.warn("process_budget_alerts failed for user {}: {}", uid, e.getMessage());
            }
        }
        return stats;
    }

    private Optional<BudgetAlert> owned(String userId, String alertId) {
        return alerts.get(alertId).filter(a -> userId.equals(a.userId));
    }

    public Optional<BudgetAlert> resolve(String userId, String alertId) {
        Optional<BudgetAlert> found = owned(userId, alertId);
        found.ifPresent(a -> {
            a.isResolved = true;
            a.resolution = BudgetAlert.RESOLUTION_USER;
            a.resolvedAt = Instant.now(clock);
            a.snoozedUntil = null;
            alerts.save(a);
            invalidateCache(userId);
        });
        return found;
    }

    public Optional<BudgetAlert> reopen(String userId, String alertId) {
        Optional<BudgetAlert> found = owned(userId, alertId);
        found.ifPresent(a -> {
            a.isResolved = false;
            a.resolution = "";
            a.resolvedAt = null;
            a.snoozedUntil = null;
            alerts.save(a);
            invalidateCache(userId);
        });
        return found;
    }

    /** Hide an open alert from the open list, badge and emails for `days` days. */
    public Optional<BudgetAlert> snooze(String userId, String alertId, int days) {
        Optional<BudgetAlert> found = owned(userId, alertId).filter(a -> !a.isResolved);
        found.ifPresent(a -> {
            a.snoozedUntil = Instant.now(clock).plus(Duration.ofDays(days));
            alerts.save(a);
        });
        return found;
    }

    public Optional<BudgetAlert> unsnooze(String userId, String alertId) {
        Optional<BudgetAlert> found = owned(userId, alertId);
        found.ifPresent(a -> {
            a.snoozedUntil = null;
            alerts.save(a);
        });
        return found;
    }

    /** Counts per lifecycle state: open, snoozed, resolved, all. */
    public Map<String, Integer> counts(String userId) {
        Map<String, Integer> counts = new LinkedHashMap<>();
        counts.put("open", 0);
        counts.put("snoozed", 0);
        counts.put("resolved", 0);
        counts.put("all", 0);
        Instant now = Instant.now(clock);
        for (BudgetAlert a : alerts.listByUser(userId, false, 500)) {
            counts.merge(a.state(now), 1, Integer::sum);
            counts.merge("all", 1, Integer::sum);
        }
        return counts;
    }
}
