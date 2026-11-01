package com.financetracker.finance.application;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.time.temporal.ChronoUnit;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import com.financetracker.access.api.UserDirectory;
import com.financetracker.access.api.UserSummary;
import com.financetracker.finance.domain.Account;
import com.financetracker.finance.domain.Commitment;
import com.financetracker.finance.domain.FinanceRepositories.CommitmentRepository;
import com.financetracker.finance.domain.FinanceRepositories.ScheduleLineRepository;
import com.financetracker.finance.domain.FinanceRepositories.TransactionRepository;
import com.financetracker.finance.domain.ScheduleLine;
import com.financetracker.finance.domain.Transaction;
import com.financetracker.notifications.api.EmailRecipient;
import com.financetracker.notifications.api.TransactionalEmails;
import com.financetracker.shared.web.Py;

/** Port of budgeting/commitment_schedule.py. */
@Service
public class CommitmentScheduleService {

    private static final Logger log = LoggerFactory.getLogger(CommitmentScheduleService.class);
    private static final Map<String, Integer> FREQ_MONTHS = Map.of("monthly", 1, "quarterly", 3, "yearly", 12);

    /** schedule_progress(commitment) */
    public record Progress(List<ScheduleLine> lines, int paymentsTotal, int paymentsCompleted, int paymentsRemaining,
            BigDecimal remainingPrincipal, String nextDueDate, BigDecimal nextDueAmount, String nextDueLineId,
            int upcomingCount, int overdueCount) {
    }

    private final ScheduleLineRepository lines;
    private final CommitmentRepository commitments;
    private final TransactionRepository transactions;
    private final UserDirectory users;
    private final TransactionalEmails emails;
    private final Clock clock;

    public CommitmentScheduleService(ScheduleLineRepository lines, CommitmentRepository commitments,
            TransactionRepository transactions, UserDirectory users, TransactionalEmails emails, Clock clock) {
        this.lines = lines;
        this.commitments = commitments;
        this.transactions = transactions;
        this.users = users;
        this.emails = emails;
        this.clock = clock;
    }

    /** Add calendar months, clamping the day to the target month's length. */
    public static LocalDate addMonths(LocalDate d, int months) {
        return d.plusMonths(months);
    }

    public static int paymentCount(int termMonths, String frequency) {
        int step = FREQ_MONTHS.getOrDefault(frequency == null || frequency.isEmpty() ? "monthly" : frequency, 1);
        int term = Math.max(termMonths, 0);
        if (term <= 0) {
            return 1;
        }
        return Math.max((term + step - 1) / step, 1);
    }

    /**
     * Build installments from start date / term / frequency / payment; the balloon is added to the
     * last one. Paid installments are always kept; outstanding ones are recreated.
     */
    public List<ScheduleLine> generate(Commitment c, boolean replace) {
        if (c == null || c.id == null) {
            return List.of();
        }
        List<ScheduleLine> existing = lines.listByCommitment(c.id);
        int expected = paymentCount(c.termMonths, c.frequency);
        if (!existing.isEmpty() && !replace && existing.size() >= expected) {
            return existing;
        }
        Map<Integer, ScheduleLine> paidBySeq = new LinkedHashMap<>();
        List<ScheduleLine> paidExtra = new ArrayList<>();
        for (ScheduleLine line : existing) {
            if (!ScheduleLine.PAID.equals(line.status)) {
                lines.delete(line);
            } else if (paidBySeq.containsKey(line.sequence)) {
                paidExtra.add(line);
            } else {
                paidBySeq.put(line.sequence, line);
            }
        }
        if (c.startDate == null || c.paymentAmount == null || c.paymentAmount.signum() <= 0) {
            List<ScheduleLine> kept = new ArrayList<>(paidBySeq.values());
            kept.addAll(paidExtra);
            kept.sort(Comparator.comparingInt(l -> l.sequence));
            return kept;
        }
        int step = FREQ_MONTHS.getOrDefault(c.frequency == null || c.frequency.isEmpty() ? "monthly" : c.frequency, 1);
        BigDecimal balloon = Dec.orZero(c.balloon);
        List<ScheduleLine> out = new ArrayList<>();
        for (int i = 0; i < expected; i++) {
            int seq = i + 1;
            if (paidBySeq.containsKey(seq)) {
                out.add(paidBySeq.remove(seq));
                continue;
            }
            BigDecimal amt = c.paymentAmount;
            if (i == expected - 1 && balloon.signum() > 0) {
                amt = amt.add(balloon);
            }
            ScheduleLine line = new ScheduleLine();
            line.commitmentId = c.id;
            line.dueDate = addMonths(c.startDate, i * step);
            line.amount = amt;
            line.status = ScheduleLine.OUTSTANDING;
            line.sequence = seq;
            lines.save(line);
            out.add(line);
        }
        out.addAll(paidBySeq.values());
        out.addAll(paidExtra);
        out.sort(Comparator.comparingInt((ScheduleLine l) -> l.sequence)
                .thenComparing(l -> l.dueDate == null ? LocalDate.MIN : l.dueDate));
        return out;
    }

    /** Generate the schedule if missing (legacy commitments). */
    public List<ScheduleLine> ensure(Commitment c) {
        return generate(c, false);
    }

    public Progress progress(Commitment c) {
        List<ScheduleLine> all = ensure(c);
        List<ScheduleLine> paid = all.stream().filter(l -> ScheduleLine.PAID.equals(l.status)).toList();
        List<ScheduleLine> outstanding = all.stream().filter(l -> ScheduleLine.OUTSTANDING.equals(l.status)).toList();
        ScheduleLine next = outstanding.isEmpty() ? null : outstanding.get(0);
        LocalDate today = LocalDate.now(clock);
        int upcoming = (int) outstanding.stream().filter(l -> l.dueDate != null && !l.dueDate.isBefore(today)).count();
        int overdue = (int) outstanding.stream().filter(l -> l.dueDate != null && l.dueDate.isBefore(today)).count();
        BigDecimal remaining = Dec.ZERO;
        for (ScheduleLine l : outstanding) {
            remaining = remaining.add(l.amount);
        }
        return new Progress(all, all.size(), paid.size(), outstanding.size(), remaining,
                next != null && next.dueDate != null ? next.dueDate.toString() : null,
                next != null ? next.amount : Dec.ZERO,
                next != null ? next.id : null,
                upcoming, overdue);
    }

    /** line_to_dict (amount left as a Decimal for decimal_to_json). */
    public Map<String, Object> lineToMap(ScheduleLine line) {
        LocalDate today = LocalDate.now(clock);
        LocalDate due = line.dueDate;
        boolean outstanding = ScheduleLine.OUTSTANDING.equals(line.status);
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", line.id);
        m.put("commitment_id", line.commitmentId);
        m.put("sequence", line.sequence);
        m.put("due_date", Py.isoformat(due));
        m.put("payment_date", Py.isoformat(line.paidDate));
        m.put("paid_date", Py.isoformat(line.paidDate));
        m.put("amount", line.amount);
        m.put("status", line.status);
        m.put("reminder_sent", line.reminderSent);
        m.put("is_overdue", outstanding && due != null && due.isBefore(today));
        m.put("days_until_due", due != null && outstanding ? ChronoUnit.DAYS.between(today, due) : null);
        return m;
    }

    public ScheduleLine markPaid(ScheduleLine line, LocalDate paidDate) {
        line.status = ScheduleLine.PAID;
        line.paidDate = paidDate != null ? paidDate : LocalDate.now(clock);
        lines.save(line);
        return line;
    }

    public ScheduleLine markOutstanding(ScheduleLine line) {
        line.status = ScheduleLine.OUTSTANDING;
        line.paidDate = null;
        line.reminderSent = false;
        lines.save(line);
        return line;
    }

    public static String lineExternalId(String lineId) {
        return "commitment_line:" + lineId;
    }

    /**
     * Mark an installment paid and record its expense transaction (reusing a linked one), so
     * savings stay correct. Returns the transaction.
     */
    public Transaction recordPayment(String userId, Commitment c, ScheduleLine line, LocalDate paidDate,
            String categoryId, Account account) {
        LocalDate date = paidDate != null ? paidDate : LocalDate.now(clock);
        String extId = lineExternalId(line.id);
        Transaction txn = transactions.getByExternalId(userId, extId).orElse(null);
        if (txn == null) {
            txn = new Transaction();
            txn.userId = userId;
            txn.date = date;
            txn.month = ReportService.monthStr(date);
            String name = c.name == null || c.name.isEmpty() ? "Commitment" : c.name;
            txn.description = name.length() > 500 ? name.substring(0, 500) : name;
            txn.categoryId = categoryId == null || categoryId.isEmpty() ? null : categoryId;
            txn.classification = null;
            txn.amount = line.amount;
            txn.currency = c.currency == null || c.currency.isEmpty() ? "USD" : c.currency;
            txn.note = "Commitment payment — " + c.name;
            txn.time = nowHhMm();
            txn.direction = "expense";
            txn.sourceAccount = account != null ? account.name : "";
            txn.incomeSourceId = account != null ? account.id : "";
            txn.commitmentId = c.id;
            txn.scheduleLineId = line.id;
            txn.externalId = extId;
            txn.includeInUtilization = categoryId != null && !categoryId.isEmpty();
            transactions.save(txn);
        }
        markPaid(line, date);
        return txn;
    }

    /** Mark an installment outstanding again and delete its linked expense transaction. */
    public ScheduleLine reversePayment(String userId, ScheduleLine line) {
        transactions.getByExternalId(userId, lineExternalId(line.id)).ifPresent(transactions::delete);
        return markOutstanding(line);
    }

    /** Keep the linked transaction's date and amount in step with an edited paid line. */
    public void syncPaymentDate(String userId, ScheduleLine line) {
        Optional<Transaction> found = transactions.getByExternalId(userId, lineExternalId(line.id));
        if (found.isEmpty()) {
            return;
        }
        Transaction txn = found.get();
        boolean changed = false;
        if (line.paidDate != null && !line.paidDate.equals(txn.date)) {
            txn.date = line.paidDate;
            txn.month = ReportService.monthStr(line.paidDate);
            changed = true;
        }
        if (txn.amount == null || txn.amount.compareTo(line.amount) != 0) {
            txn.amount = line.amount;
            changed = true;
        }
        if (changed) {
            transactions.save(txn);
        }
    }

    String nowHhMm() {
        return LocalTime.now(clock).format(DateTimeFormatter.ofPattern("HH:mm"));
    }

    /**
     * Email reminders for outstanding installments inside each commitment's reminder window;
     * marks reminder_sent so each installment emails once. Returns the number sent.
     */
    public int evaluateReminders(List<UserSummary> forUsers) {
        int sent = 0;
        LocalDate today = LocalDate.now(clock);
        for (UserSummary u : forUsers) {
            for (Commitment c : commitments.listByUser(u.userId())) {
                if (!c.reminderEnabled) {
                    continue;
                }
                int daysBefore = Math.max(c.reminderDaysBefore, 0);
                for (ScheduleLine line : ensure(c)) {
                    if (!ScheduleLine.OUTSTANDING.equals(line.status) || line.dueDate == null || line.reminderSent) {
                        continue;
                    }
                    LocalDate windowStart = line.dueDate.minusDays(daysBefore);
                    if (!today.isBefore(windowStart) && !today.isAfter(line.dueDate)) {
                        if (sendReminder(u, c, line)) {
                            line.reminderSent = true;
                            lines.save(line);
                            sent++;
                        }
                    }
                }
            }
        }
        return sent;
    }

    public int evaluateReminders(String userId) {
        return users.findById(userId).map(u -> evaluateReminders(List.of(u))).orElse(0);
    }

    private boolean sendReminder(UserSummary user, Commitment c, ScheduleLine line) {
        if (user.email() == null || user.email().isEmpty()) {
            log.info("No email for user {}; skipping commitment reminder {}/{}", user.id(), c.id, line.id);
            return false;
        }
        try {
            return emails.commitmentReminder(recipient(user), c.name,
                    line.dueDate != null ? line.dueDate.toString() : "—", Py.dec(line.amount), line.sequence);
        } catch (RuntimeException e) {
            log.warn("Failed to send commitment reminder email: {}", e.getMessage());
            return false;
        }
    }

    static EmailRecipient recipient(UserSummary u) {
        return new EmailRecipient(u.id(), u.email(), u.firstName(), u.lastName(), u.username());
    }
}
