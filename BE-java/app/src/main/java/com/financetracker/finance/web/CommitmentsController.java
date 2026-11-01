package com.financetracker.finance.web;

import static com.financetracker.finance.web.FinanceJson.dec;
import static com.financetracker.finance.web.FinanceJson.uid;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import com.financetracker.finance.application.AlertService;
import com.financetracker.finance.application.CategoryAccess;
import com.financetracker.finance.application.CommitmentScheduleService;
import com.financetracker.finance.application.Dec;
import com.financetracker.finance.application.PlanTriggerService;
import com.financetracker.finance.domain.Account;
import com.financetracker.finance.domain.Commitment;
import com.financetracker.finance.domain.FinanceRepositories.AccountRepository;
import com.financetracker.finance.domain.FinanceRepositories.CommitmentRepository;
import com.financetracker.finance.domain.FinanceRepositories.FinancialStandingRepository;
import com.financetracker.finance.domain.FinanceRepositories.ScheduleLineRepository;
import com.financetracker.finance.domain.FinancialStanding;
import com.financetracker.finance.domain.ScheduleLine;
import com.financetracker.finance.domain.Transaction;
import com.financetracker.shared.error.ApiException;
import com.financetracker.shared.locale.LocaleConstants;
import com.financetracker.shared.web.Field;
import com.financetracker.shared.web.Py;
import com.financetracker.shared.web.RequestData;

/** Commitments (loans), their installment schedules, and financial standing snapshots. */
@RestController
@RequestMapping("/api/v1/budgeting")
class CommitmentsController {

    private static final List<String> FREQUENCIES = List.of("monthly", "quarterly", "yearly");
    private static final Set<String> SCHEDULE_FIELDS = Set.of("start_date", "term_months", "frequency", "payment_amount", "balloon");

    private final CommitmentRepository commitments;
    private final ScheduleLineRepository lines;
    private final FinancialStandingRepository standings;
    private final AccountRepository accounts;
    private final CommitmentScheduleService schedules;
    private final PlanTriggerService planTriggers;
    private final AlertService alerts;
    private final CategoryAccess categoryAccess;
    private final Clock clock;

    CommitmentsController(CommitmentRepository commitments, ScheduleLineRepository lines,
            FinancialStandingRepository standings, AccountRepository accounts, CommitmentScheduleService schedules,
            PlanTriggerService planTriggers, AlertService alerts, CategoryAccess categoryAccess, Clock clock) {
        this.commitments = commitments;
        this.lines = lines;
        this.standings = standings;
        this.accounts = accounts;
        this.schedules = schedules;
        this.planTriggers = planTriggers;
        this.alerts = alerts;
        this.categoryAccess = categoryAccess;
        this.clock = clock;
    }

    private Commitment owned(String uid, String pk) {
        return commitments.get(pk).filter(c -> uid.equals(c.userId)).orElseThrow(ApiException::notFound);
    }

    private ScheduleLine ownedLine(Commitment c, String lineId) {
        return lines.get(lineId).filter(l -> c.id.equals(l.commitmentId))
                .orElseThrow(() -> ApiException.notFound("Schedule line not found."));
    }

    private Map<String, Object> commitmentJson(Commitment c, CommitmentScheduleService.Progress p, boolean withLineId) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", c.id);
        m.put("name", c.name);
        m.put("amount", c.amount);
        m.put("start_date", Py.isoformat(c.startDate));
        m.put("term_months", c.termMonths);
        m.put("frequency", c.frequency);
        m.put("payment_amount", c.paymentAmount);
        m.put("balloon", c.balloon);
        m.put("currency", c.currency == null || c.currency.isEmpty() ? "USD" : c.currency);
        m.put("reminder_enabled", c.reminderEnabled);
        m.put("reminder_days_before", c.reminderDaysBefore);
        m.put("remaining_principal", p.remainingPrincipal());
        m.put("payments_total", p.paymentsTotal());
        m.put("payments_completed", p.paymentsCompleted());
        m.put("payments_remaining", p.paymentsRemaining());
        m.put("next_due_date", p.nextDueDate());
        m.put("next_due_amount", p.nextDueAmount());
        if (withLineId) {
            m.put("next_due_line_id", p.nextDueLineId());
        }
        m.put("upcoming_count", p.upcomingCount());
        m.put("overdue_count", p.overdueCount());
        return m;
    }

    @GetMapping("/commitments/")
    List<Map<String, Object>> list() {
        String uid = uid();
        try {
            // Opportunistically send due reminders while the user is active.
            schedules.evaluateReminders(uid);
        } catch (RuntimeException ignored) {
            // best effort, as in Django
        }
        Set<String> seen = new HashSet<>();
        List<Map<String, Object>> out = new ArrayList<>();
        for (Commitment c : commitments.listByUser(uid)) {
            if (c.id == null || !seen.add(c.id)) {
                continue;
            }
            out.add(dec(commitmentJson(c, schedules.progress(c), true)));
        }
        return out;
    }

    /** CommitmentSerializer fields (partial for PATCH). */
    private static RequestData parseCommitment(Map<String, Object> body, boolean partial) {
        RequestData d = partial ? RequestData.partial(body) : RequestData.of(body);
        d.string("name", Field.required().maxLength(200));
        d.decimal("amount", Field.required().digits(12, 2));
        d.date("start_date", Field.required());
        d.integer("term_months", Field.required());
        d.choice("frequency", FREQUENCIES, Field.required());
        d.decimal("payment_amount", Field.required().digits(12, 2));
        d.decimal("balloon", Field.withDefault(BigDecimal.ZERO).digits(12, 2));
        d.choice("currency", LocaleConstants.CURRENCY_CODES, Field.withDefault("USD"));
        d.bool("reminder_enabled", Field.withDefault(true));
        d.integer("reminder_days_before", Field.withDefault(3).min(0).max(90));
        d.validate();
        return d;
    }

    private static void apply(Commitment c, Map<String, Object> cd) {
        cd.forEach((field, value) -> {
            switch (field) {
                case "name" -> c.name = (String) value;
                case "amount" -> c.amount = (BigDecimal) value;
                case "start_date" -> c.startDate = (LocalDate) value;
                case "term_months" -> c.termMonths = (Integer) value;
                case "frequency" -> c.frequency = (String) value;
                case "payment_amount" -> c.paymentAmount = (BigDecimal) value;
                case "balloon" -> c.balloon = value == null ? Dec.ZERO : (BigDecimal) value;
                case "currency" -> c.currency = value == null || "".equals(value) ? "USD" : (String) value;
                case "reminder_enabled" -> c.reminderEnabled = (Boolean) value;
                case "reminder_days_before" -> c.reminderDaysBefore = (Integer) value;
                default -> { }
            }
        });
    }

    @PostMapping("/commitments/")
    ResponseEntity<Map<String, Object>> create(@RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        RequestData d = parseCommitment(body, false);
        Commitment c = new Commitment();
        c.userId = uid;
        apply(c, d.validated());
        commitments.save(c);
        schedules.generate(c, true);
        planTriggers.onCommitmentChange(uid, c.id, "created", c.name);
        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("id", c.id));
    }

    @GetMapping("/commitments/{pk}/")
    Map<String, Object> detail(@PathVariable String pk) {
        Commitment c = owned(uid(), pk);
        CommitmentScheduleService.Progress p = schedules.progress(c);
        Set<String> seen = new HashSet<>();
        List<Map<String, Object>> schedule = new ArrayList<>();
        for (ScheduleLine l : p.lines()) {
            if (l.id != null && !seen.add(l.id)) {
                continue;
            }
            schedule.add(schedules.lineToMap(l));
        }
        Map<String, Object> m = commitmentJson(c, p, false);
        m.put("schedule", schedule);
        return dec(m);
    }

    @PatchMapping("/commitments/{pk}/")
    Map<String, Object> update(@PathVariable String pk, @RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        Commitment c = owned(uid, pk);
        RequestData d = parseCommitment(body, true);
        apply(c, d.validated());
        boolean touchedSchedule = d.validated().keySet().stream().anyMatch(SCHEDULE_FIELDS::contains);
        commitments.save(c);
        if (touchedSchedule) {
            // Rebuild outstanding installments; paid ones (and their transactions) are kept.
            schedules.generate(c, true);
            planTriggers.onCommitmentChange(uid, c.id, "updated", c.name);
        }
        return Map.of("id", c.id);
    }

    @DeleteMapping("/commitments/{pk}/")
    ResponseEntity<Void> delete(@PathVariable String pk) {
        String uid = uid();
        Commitment c = owned(uid, pk);
        lines.deleteByCommitment(c.id);
        commitments.delete(c);
        planTriggers.onCommitmentChange(uid, c.id, "deleted", c.name);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/commitments/{pk}/schedule/")
    List<Map<String, Object>> schedule(@PathVariable String pk) {
        Commitment c = owned(uid(), pk);
        return dec(schedules.ensure(c).stream().map(schedules::lineToMap).toList());
    }

    @PostMapping("/commitments/{pk}/schedule/{lineId}/pay/")
    Map<String, Object> pay(@PathVariable String pk, @PathVariable String lineId,
            @RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        Commitment c = owned(uid, pk);
        ScheduleLine line = ownedLine(c, lineId);
        Map<String, Object> data = body == null ? Map.of() : body;
        RequestData d = RequestData.of(data);
        LocalDate paidDate = d.date("paid_date", Field.optional());
        LocalDate paymentDate = d.date("payment_date", Field.optional());
        d.validate();
        if (paymentDate != null && paidDate == null) {
            paidDate = paymentDate;
        }
        if (paidDate == null) {
            paidDate = LocalDate.now(clock);
        }
        String categoryId = Py.truthy(data.get("category_id")) ? Py.str(data.get("category_id")).strip() : "";
        if (!categoryId.isEmpty()) {
            String cid = categoryId;
            categoryId = categoryAccess.visibleCategory(uid, cid).orElseThrow(() -> new ApiException(HttpStatus.BAD_REQUEST,
                    FinanceJson.fieldError("category_id", CategoriesController.categoryIdError(categoryAccess, uid, cid)))).id;
        }
        Account acc = null;
        String accountId = TransactionsController.parseAccountId(data);
        if (!accountId.isEmpty()) {
            acc = TransactionsController.resolveAccount(accounts, uid, accountId);
        }
        Transaction txn = schedules.recordPayment(uid, c, line, paidDate, categoryId.isEmpty() ? null : categoryId, acc);
        alerts.trigger(uid, paidDate.getYear(), paidDate.getMonthValue());
        Map<String, Object> out = schedules.lineToMap(line);
        out.put("transaction_id", txn.id);
        return dec(out);
    }

    @PatchMapping("/commitments/{pk}/schedule/{lineId}/")
    Map<String, Object> updateLine(@PathVariable String pk, @PathVariable String lineId,
            @RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        Commitment c = owned(uid, pk);
        ScheduleLine line = ownedLine(c, lineId);
        RequestData d = RequestData.partial(body);
        LocalDate dueDate = d.date("due_date", Field.optional());
        LocalDate paymentDate = d.date("payment_date", Field.optional().allowNull());
        LocalDate paidDate = d.date("paid_date", Field.optional().allowNull());
        BigDecimal amount = d.decimal("amount", Field.optional().digits(12, 2));
        String status = d.choice("status", List.of("outstanding", "paid"), Field.optional());
        d.validate();
        boolean hasPaidDate = d.provided("paid_date");
        if (d.provided("payment_date") && !hasPaidDate) {
            paidDate = paymentDate;
            hasPaidDate = true;
        }
        boolean wasPaid = ScheduleLine.PAID.equals(line.status);
        if (d.provided("due_date")) {
            line.dueDate = dueDate;
            line.reminderSent = false;
        }
        if (d.provided("amount")) {
            line.amount = amount;
        }
        String targetStatus = line.status;
        LocalDate targetPaidDate = line.paidDate;
        if (d.provided("status")) {
            targetStatus = status;
            if (ScheduleLine.OUTSTANDING.equals(targetStatus)) {
                targetPaidDate = null;
            }
        }
        if (hasPaidDate) {
            targetPaidDate = paidDate;
            targetStatus = paidDate != null ? ScheduleLine.PAID
                    : ScheduleLine.PAID.equals(targetStatus) ? ScheduleLine.OUTSTANDING : targetStatus;
        }
        if (ScheduleLine.PAID.equals(targetStatus) && !wasPaid) {
            schedules.recordPayment(uid, c, line, targetPaidDate != null ? targetPaidDate : LocalDate.now(clock), null, null);
        } else if (!ScheduleLine.PAID.equals(targetStatus) && wasPaid) {
            schedules.reversePayment(uid, line);
            if (!line.status.equals(targetStatus)) {
                line.status = targetStatus;
                lines.save(line);
            }
        } else {
            line.status = targetStatus;
            line.paidDate = targetPaidDate;
            lines.save(line);
            if (ScheduleLine.PAID.equals(line.status)) {
                schedules.syncPaymentDate(uid, line);
            }
        }
        return dec(schedules.lineToMap(line));
    }

    @PostMapping("/commitments/{pk}/schedule/{lineId}/unpay/")
    Map<String, Object> unpay(@PathVariable String pk, @PathVariable String lineId) {
        String uid = uid();
        Commitment c = owned(uid, pk);
        ScheduleLine line = ownedLine(c, lineId);
        schedules.reversePayment(uid, line);
        alerts.trigger(uid, null, null);
        return dec(schedules.lineToMap(line));
    }

    @PostMapping("/commitments/{pk}/regenerate-schedule/")
    Map<String, Object> regenerate(@PathVariable String pk) {
        String uid = uid();
        Commitment c = owned(uid, pk);
        List<ScheduleLine> generated = schedules.generate(c, true);
        planTriggers.onCommitmentChange(uid, c.id, "updated", c.name);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("id", c.id);
        out.put("payments_total", generated.size());
        out.put("schedule", generated.stream().map(schedules::lineToMap).toList());
        return dec(out);
    }

    // ---------------------------------------------------------------- financial standing

    @GetMapping("/financial-standing/")
    List<Map<String, Object>> standings() {
        List<Map<String, Object>> out = new ArrayList<>();
        for (FinancialStanding s : standings.listByUser(uid())) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", s.id);
            m.put("snapshot_date", Py.isoformat(s.snapshotDate));
            m.put("total_assets", s.totalAssets);
            m.put("current_assets", s.currentAssets);
            m.put("fixed_assets", s.fixedAssets);
            m.put("total_liabilities", s.totalLiabilities);
            m.put("short_term_liabilities", s.shortTermLiabilities);
            m.put("long_term_liabilities", s.longTermLiabilities);
            m.put("notes", s.notes);
            out.add(dec(m));
        }
        return out;
    }

    @PostMapping("/financial-standing/")
    ResponseEntity<Map<String, Object>> createStanding(@RequestBody(required = false) Map<String, Object> body) {
        RequestData d = RequestData.of(body);
        LocalDate snapshot = d.date("snapshot_date", Field.required());
        BigDecimal[] values = new BigDecimal[6];
        String[] names = {"total_assets", "current_assets", "fixed_assets", "total_liabilities",
                "short_term_liabilities", "long_term_liabilities"};
        for (int i = 0; i < names.length; i++) {
            values[i] = d.decimal(names[i], Field.withDefault(BigDecimal.ZERO).digits(14, 2));
        }
        String notes = d.string("notes", Field.withDefault("").allowBlank());
        d.validate();
        FinancialStanding s = new FinancialStanding();
        s.userId = uid();
        s.snapshotDate = snapshot;
        s.totalAssets = Dec.orZero(values[0]);
        s.currentAssets = Dec.orZero(values[1]);
        s.fixedAssets = Dec.orZero(values[2]);
        s.totalLiabilities = Dec.orZero(values[3]);
        s.shortTermLiabilities = Dec.orZero(values[4]);
        s.longTermLiabilities = Dec.orZero(values[5]);
        s.notes = notes == null ? "" : notes;
        standings.save(s);
        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("id", s.id));
    }
}
