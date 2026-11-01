package com.financetracker.finance.web;

import static com.financetracker.finance.web.FinanceJson.queryInt;
import static com.financetracker.finance.web.FinanceJson.uid;

import java.time.Clock;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.financetracker.finance.application.AlertService;
import com.financetracker.finance.application.CategoryAccess;
import com.financetracker.finance.application.CommitmentScheduleService;
import com.financetracker.finance.application.ReportService;
import com.financetracker.finance.domain.Account;
import com.financetracker.finance.domain.BudgetAlert;
import com.financetracker.finance.domain.Commitment;
import com.financetracker.finance.domain.FinanceRepositories.AccountRepository;
import com.financetracker.finance.domain.FinanceRepositories.BudgetAlertRepository;
import com.financetracker.finance.domain.FinanceRepositories.CommitmentRepository;
import com.financetracker.finance.domain.FinanceRepositories.TransactionRepository;
import com.financetracker.finance.domain.ScheduleLine;
import com.financetracker.finance.domain.Transaction;
import com.financetracker.shared.error.ApiException;
import com.financetracker.shared.web.Py;
import com.financetracker.shared.web.RequestData;

/** /budgeting/alerts/* */
@RestController
@RequestMapping("/api/v1/budgeting/alerts")
class AlertsController {

    private static final int MAX_BULK_IDS = 300;

    private final AlertService alerts;
    private final BudgetAlertRepository alertRepository;
    private final CommitmentRepository commitments;
    private final TransactionRepository transactions;
    private final AccountRepository accounts;
    private final CommitmentScheduleService schedules;
    private final CategoryAccess categoryAccess;
    private final Clock clock;

    AlertsController(AlertService alerts, BudgetAlertRepository alertRepository, CommitmentRepository commitments,
            TransactionRepository transactions, AccountRepository accounts, CommitmentScheduleService schedules,
            CategoryAccess categoryAccess, Clock clock) {
        this.alerts = alerts;
        this.alertRepository = alertRepository;
        this.commitments = commitments;
        this.transactions = transactions;
        this.accounts = accounts;
        this.schedules = schedules;
        this.categoryAccess = categoryAccess;
        this.clock = clock;
    }

    @GetMapping("/")
    List<Map<String, Object>> list(@RequestParam(defaultValue = "open") String show,
            @RequestParam(required = false) String year, @RequestParam(required = false) String month,
            @RequestParam(defaultValue = "") String refresh) {
        String uid = uid();
        LocalDate today = LocalDate.now(clock);
        int y = queryInt(year, today.getYear());
        int m = queryInt(month, today.getMonthValue());
        if (List.of("1", "true", "yes").contains(refresh.toLowerCase())) {
            alerts.refresh(uid, y, m, true);
        }
        Instant now = Instant.now(clock);
        List<BudgetAlert> rows = alertRepository.listByUser(uid, false, 300);
        if (!"all".equals(show)) {
            String wanted = "snoozed".equals(show) || "resolved".equals(show) ? show : "open";
            rows = rows.stream().filter(a -> wanted.equals(a.state(now))).toList();
        }
        return rows.stream().map(a -> FinanceJson.alert(a, now)).toList();
    }

    @GetMapping("/count/")
    Map<String, Object> count() {
        Map<String, Integer> counts = alerts.counts(uid());
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("count", counts.get("open"));
        out.putAll(counts);
        return out;
    }

    private static Integer snoozeDays(Map<String, Object> data) {
        Object raw = data.containsKey("days") ? data.get("days") : 1;
        Integer days = raw == null ? null : RequestData.parseInt(raw);
        return days != null && AlertService.SNOOZE_DAY_CHOICES.contains(days) ? days : null;
    }

    private static ApiException badDays() {
        return ApiException.field("days", "Choose one of " + AlertService.SNOOZE_DAY_CHOICES.stream()
                .map(String::valueOf).collect(Collectors.joining(", ")) + " days.");
    }

    @PostMapping("/{pk}/resolve/")
    Map<String, Object> resolve(@PathVariable String pk) {
        BudgetAlert a = alerts.resolve(uid(), pk).orElseThrow(ApiException::notFound);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("id", a.id);
        out.put("is_resolved", true);
        return out;
    }

    @PostMapping("/{pk}/reopen/")
    Map<String, Object> reopen(@PathVariable String pk) {
        return FinanceJson.alert(alerts.reopen(uid(), pk).orElseThrow(ApiException::notFound), Instant.now(clock));
    }

    @PostMapping("/{pk}/snooze/")
    Map<String, Object> snooze(@PathVariable String pk, @RequestBody(required = false) Map<String, Object> body) {
        Integer days = snoozeDays(body == null ? Map.of() : body);
        if (days == null) {
            throw badDays();
        }
        BudgetAlert a = alerts.snooze(uid(), pk, days)
                .orElseThrow(() -> ApiException.notFound("Not found or already resolved."));
        return FinanceJson.alert(a, Instant.now(clock));
    }

    @DeleteMapping("/{pk}/snooze/")
    Map<String, Object> unsnooze(@PathVariable String pk) {
        return FinanceJson.alert(alerts.unsnooze(uid(), pk).orElseThrow(ApiException::notFound), Instant.now(clock));
    }

    /** {"action": resolve|reopen|snooze|unsnooze, "ids": [...], "days": 1|3|7} on the caller's alerts. */
    @PostMapping("/bulk/")
    Map<String, Object> bulk(@RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        Map<String, Object> data = body == null ? Map.of() : body;
        String action = Py.truthy(data.get("action")) ? Py.str(data.get("action")).strip() : "";
        Object ids = Py.truthy(data.get("ids")) ? data.get("ids") : List.of();
        if (!(ids instanceof List<?> idList) || idList.isEmpty()) {
            throw ApiException.field("ids", "Select at least one alert.");
        }
        if (idList.size() > MAX_BULK_IDS) {
            throw ApiException.field("ids", "At most " + MAX_BULK_IDS + " alerts at once.");
        }
        Function<String, Optional<BudgetAlert>> apply;
        switch (action) {
            case "snooze" -> {
                Integer days = snoozeDays(data);
                if (days == null) {
                    throw badDays();
                }
                apply = pk -> alerts.snooze(uid, pk, days);
            }
            case "resolve" -> apply = pk -> alerts.resolve(uid, pk);
            case "reopen" -> apply = pk -> alerts.reopen(uid, pk);
            case "unsnooze" -> apply = pk -> alerts.unsnooze(uid, pk);
            default -> throw ApiException.field("action", "Use resolve, reopen, snooze or unsnooze.");
        }
        Set<String> unique = new LinkedHashSet<>();
        idList.forEach(i -> unique.add(Py.str(i)));
        List<String> updated = new ArrayList<>();
        List<String> failed = new ArrayList<>();
        for (String pk : unique) {
            (apply.apply(pk).isPresent() ? updated : failed).add(pk);
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("action", action);
        out.put("updated", updated);
        out.put("failed", failed);
        return out;
    }

    /** From a commitment due-date alert: record the expense (in utilization) and mark the installment paid. */
    @PostMapping("/{pk}/record-commitment/")
    ResponseEntity<Map<String, Object>> recordCommitment(@PathVariable String pk,
            @RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        Map<String, Object> data = body == null ? Map.of() : body;
        BudgetAlert alert = alertRepository.get(pk).filter(a -> uid.equals(a.userId)).orElseThrow(ApiException::notFound);
        if (alert.isResolved) {
            throw ApiException.badRequest("Alert already resolved.");
        }
        Object record = data.containsKey("record_expense") ? data.get("record_expense") : Boolean.TRUE;
        if (Boolean.FALSE.equals(record) || "false".equals(record) || "0".equals(record)
                || (record instanceof Number n && n.doubleValue() == 0d)) {
            alerts.resolve(uid, pk);
            Map<String, Object> out = new LinkedHashMap<>();
            out.put("id", pk);
            out.put("recorded", false);
            out.put("is_resolved", true);
            return ResponseEntity.ok(out);
        }
        String categoryId = Py.truthy(data.get("category_id")) ? Py.str(data.get("category_id")).strip() : "";
        if (categoryId.isEmpty()) {
            throw ApiException.field("category_id", "Category is required to add to expenses and utilization.");
        }
        String cid = categoryId;
        categoryId = categoryAccess.visibleCategory(uid, cid).orElseThrow(() -> new ApiException(HttpStatus.BAD_REQUEST,
                FinanceJson.fieldError("category_id", CategoriesController.categoryIdError(categoryAccess, uid, cid)))).id;
        Account acc = null;
        String accountId = TransactionsController.parseAccountId(data);
        if (!accountId.isEmpty()) {
            acc = TransactionsController.resolveAccount(accounts, uid, accountId);
        }
        String commitmentId = alert.commitmentId == null ? "" : alert.commitmentId.strip();
        String scheduleLineId = alert.scheduleLineId == null ? "" : alert.scheduleLineId.strip();
        if (commitmentId.isEmpty() && alert.categoryId != null && alert.categoryId.startsWith("commitment:")) {
            commitmentId = alert.categoryId.split(":", 2)[1];
        }
        if (scheduleLineId.isEmpty() && alert.fingerprint != null && !alert.fingerprint.isEmpty()) {
            String[] parts = alert.fingerprint.split("\\|", -1);
            if (parts.length >= 3 && "due".equals(parts[1])) {
                scheduleLineId = parts[2];
            }
        }
        if (commitmentId.isEmpty() || scheduleLineId.isEmpty()) {
            throw ApiException.badRequest("Alert is missing commitment installment details.");
        }
        String commitmentKey = commitmentId;
        Commitment c = commitments.get(commitmentKey).filter(x -> uid.equals(x.userId))
                .orElseThrow(() -> ApiException.field("commitment_id", "Commitment not found."));
        String lineKey = scheduleLineId;
        ScheduleLine paidLine = schedules.progress(c).lines().stream()
                .filter(l -> lineKey.equals(l.id) && ScheduleLine.OUTSTANDING.equals(l.status)).findFirst()
                .orElseThrow(() -> ApiException.field("commitment_id", "This installment is no longer outstanding."));
        String extId = CommitmentScheduleService.lineExternalId(scheduleLineId);
        if (transactions.existsByUserIdAndExternalId(uid, extId)) {
            alerts.resolve(uid, pk);
            Map<String, Object> err = new LinkedHashMap<>();
            err.put("detail", "Transaction already recorded for this installment.");
            err.put("recorded", false);
            throw new ApiException(HttpStatus.CONFLICT, err);
        }
        String paymentRaw = Py.truthy(data.get("payment_date")) ? Py.str(data.get("payment_date")).strip() : "";
        LocalDate txnDate = LocalDate.now(clock);
        if (!paymentRaw.isEmpty()) {
            try {
                txnDate = LocalDate.parse(paymentRaw.length() > 10 ? paymentRaw.substring(0, 10) : paymentRaw);
            } catch (RuntimeException e) {
                txnDate = LocalDate.now(clock);
            }
        }
        String name = (alert.commitmentName != null && !alert.commitmentName.isEmpty() ? alert.commitmentName
                : c.name != null && !c.name.isEmpty() ? c.name : "Commitment").strip();
        Transaction t = new Transaction();
        t.userId = uid;
        t.date = txnDate;
        t.month = ReportService.monthStr(txnDate);
        t.description = name.length() > 500 ? name.substring(0, 500) : name;
        t.categoryId = categoryId;
        t.classification = null;
        t.amount = paidLine.amount;
        t.currency = c.currency == null || c.currency.isEmpty() ? "USD" : c.currency;
        t.note = "Commitment payment — " + name;
        t.time = java.time.LocalTime.now(clock).format(java.time.format.DateTimeFormatter.ofPattern("HH:mm"));
        t.direction = "expense";
        t.sourceAccount = acc != null ? acc.name : "";
        t.incomeSourceId = acc != null ? acc.id : "";
        t.commitmentId = commitmentId;
        t.scheduleLineId = scheduleLineId;
        t.externalId = extId;
        t.includeInUtilization = true;
        transactions.save(t);
        schedules.markPaid(paidLine, txnDate);
        alerts.refresh(uid, txnDate.getYear(), txnDate.getMonthValue(), true);
        alerts.resolve(uid, pk);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("id", t.id);
        out.put("recorded", true);
        out.put("transaction", FinanceJson.transaction(t));
        out.put("alert_id", pk);
        out.put("is_resolved", true);
        return ResponseEntity.status(HttpStatus.CREATED).body(out);
    }
}
