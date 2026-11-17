package com.financetracker.finance.web;

import static com.financetracker.finance.web.FinanceJson.fieldError;
import static com.financetracker.finance.web.FinanceJson.transaction;

import java.io.IOException;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.TreeSet;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

import com.financetracker.access.api.UserDirectory;
import com.financetracker.access.api.UserLocale;
import com.financetracker.finance.application.AlertService;
import com.financetracker.finance.application.CategoryAccess;
import com.financetracker.finance.application.CommitmentScheduleService;
import com.financetracker.finance.application.PersonalBudgetAccess;
import com.financetracker.finance.application.ReportService;
import com.financetracker.finance.application.StatementFormats;
import com.financetracker.finance.application.StatementImporter;
import com.financetracker.finance.domain.Account;
import com.financetracker.finance.domain.Category;
import com.financetracker.finance.domain.Commitment;
import com.financetracker.finance.domain.FinanceRepositories.AccountRepository;
import com.financetracker.finance.domain.FinanceRepositories.CommitmentRepository;
import com.financetracker.finance.domain.FinanceRepositories.ScheduleLineRepository;
import com.financetracker.finance.domain.FinanceRepositories.TransactionRepository;
import com.financetracker.finance.domain.ScheduleLine;
import com.financetracker.finance.domain.Transaction;
import com.financetracker.shared.config.AppProperties;
import com.financetracker.shared.error.ApiException;
import com.financetracker.shared.locale.LocaleConstants;
import com.financetracker.shared.security.AuthUser;
import com.financetracker.shared.security.CurrentUser;
import com.financetracker.shared.web.Field;
import com.financetracker.shared.web.Py;
import com.financetracker.shared.web.RequestData;

/** /budgeting/transactions/* (TransactionListCreateView, TransactionDetailView, TransactionUploadView). */
@RestController
@RequestMapping("/api/v1/budgeting/transactions")
class TransactionsController {

    private final TransactionRepository transactions;
    private final AccountRepository accounts;
    private final CommitmentRepository commitments;
    private final ScheduleLineRepository scheduleLines;
    private final CommitmentScheduleService schedules;
    private final CategoryAccess categoryAccess;
    private final PersonalBudgetAccess budgetAccess;
    private final ReportService reports;
    private final AlertService alerts;
    private final UserDirectory users;
    private final AppProperties props;

    TransactionsController(TransactionRepository transactions, AccountRepository accounts, CommitmentRepository commitments,
            ScheduleLineRepository scheduleLines, CommitmentScheduleService schedules, CategoryAccess categoryAccess,
            PersonalBudgetAccess budgetAccess, ReportService reports, AlertService alerts, UserDirectory users,
            AppProperties props) {
        this.transactions = transactions;
        this.accounts = accounts;
        this.commitments = commitments;
        this.scheduleLines = scheduleLines;
        this.schedules = schedules;
        this.categoryAccess = categoryAccess;
        this.budgetAccess = budgetAccess;
        this.reports = reports;
        this.alerts = alerts;
        this.users = users;
        this.props = props;
    }

    /** views/budgeting._resolve_account */
    static Account resolveAccount(AccountRepository accounts, String userId, String accountId) {
        if (accountId == null || accountId.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST,
                    fieldError("account_id", "Select the account this transaction was done from."));
        }
        return accounts.get(accountId).filter(a -> userId.equals(a.userId))
                .orElseThrow(() -> new ApiException(HttpStatus.BAD_REQUEST, fieldError("account_id", "Account not found.")));
    }

    /** _parse_account_id(data) */
    static String parseAccountId(Map<String, Object> data) {
        if (data == null) {
            return "";
        }
        Object v = Py.truthy(data.get("account_id")) ? data.get("account_id") : data.get("income_source_id");
        return Py.truthy(v) ? Py.str(v).strip() : "";
    }

    private String budgetLinkError(String userId, String budgetId) {
        if (budgetId == null || budgetId.isEmpty()) {
            return null;
        }
        try {
            budgetAccess.requireEdit(userId, budgetId);
        } catch (PersonalBudgetAccess.Denied e) {
            return e.getMessage() == null || e.getMessage().isEmpty()
                    ? "You do not have permission to modify this budget." : e.getMessage();
        }
        return null;
    }

    /** _transaction_access: the owner, or an editor of the shared budget it belongs to. */
    private Optional<Transaction> accessible(String userId, String pk) {
        return transactions.get(pk).filter(t -> {
            if (userId.equals(t.userId)) {
                return true;
            }
            String bid = t.budgetId == null ? "" : t.budgetId.strip();
            if (bid.isEmpty()) {
                return false;
            }
            try {
                budgetAccess.requireEdit(userId, bid);
                return true;
            } catch (PersonalBudgetAccess.Denied e) {
                return false;
            }
        });
    }

    private Category requireSubcategory(String userId, String categoryId) {
        return categoryAccess.visibleCategory(userId, categoryId).orElseThrow(() -> new ApiException(HttpStatus.BAD_REQUEST,
                fieldError("category_id", CategoriesController.categoryIdError(categoryAccess, userId, categoryId))));
    }

    @GetMapping("/")
    List<Map<String, Object>> list(@RequestParam(required = false) String month) {
        return transactions.listByUser(FinanceJson.uid(), month, 500).stream().map(FinanceJson::transaction).toList();
    }

    private static String trimmedOrNull(String v) {
        if (v == null) {
            return null;
        }
        String s = v.strip();
        return s.isEmpty() ? null : s;
    }

    @PostMapping("/")
    ResponseEntity<Map<String, Object>> create(@RequestBody(required = false) Map<String, Object> body) {
        AuthUser user = CurrentUser.require();
        String uid = user.userId();
        RequestData d = RequestData.of(body);
        LocalDate date = d.date("date", Field.required());
        String time = d.string("time", Field.withDefault("").allowBlank().maxLength(8));
        String description = d.string("description", Field.withDefault("").allowBlank().maxLength(500));
        String categoryRaw = d.string("category_id", Field.optional().allowNull().allowBlank());
        d.choice("classification", List.of("", "fixed", "variable"), Field.optional().allowBlank().allowNull());
        BigDecimal amount = d.decimal("amount", Field.required().digits(12, 2));
        String currency = d.choice("currency", LocaleConstants.CURRENCY_CODES, Field.withDefault("USD"));
        String note = d.string("note", Field.withDefault("").allowBlank().maxLength(1000));
        String direction = d.choice("direction", List.of("income", "expense", "transfer"), Field.required());
        d.string("source_account", Field.withDefault("").allowBlank());
        String accountRaw = d.string("account_id", Field.optional().allowNull().allowBlank());
        String incomeSourceRaw = d.string("income_source_id", Field.optional().allowNull().allowBlank());
        String commitmentRaw = d.string("commitment_id", Field.optional().allowNull().allowBlank());
        String lineRaw = d.string("schedule_line_id", Field.optional().allowNull().allowBlank());
        Boolean include = d.bool("include_in_utilization", Field.withDefault(false));
        String budgetRaw = d.string("budget_id", Field.optional().allowNull().allowBlank());
        String budgetCategoryRaw = d.string("budget_category_id", Field.optional().allowNull().allowBlank());
        d.validate();

        // TransactionSerializer.validate
        String accountId = (accountRaw != null && !accountRaw.isEmpty() ? accountRaw
                : incomeSourceRaw != null ? incomeSourceRaw : "").strip();
        String commitmentCheck = commitmentRaw == null ? "" : commitmentRaw.strip();
        if ("income".equals(direction) && description.strip().isEmpty()) {
            throw ApiException.field("description", "Enter what this income is (e.g. Salary).");
        }
        if (accountId.isEmpty()) {
            throw ApiException.field("account_id", "Select the account this transaction was done from.");
        }
        if ("expense".equals(direction) && commitmentCheck.isEmpty() && description.strip().isEmpty()) {
            throw ApiException.field("description", "Merchant or description is required for expenses.");
        }

        String categoryId = categoryRaw == null || categoryRaw.isEmpty() ? null : categoryRaw;
        String commitmentId = trimmedOrNull(commitmentRaw);
        String scheduleLineId = trimmedOrNull(lineRaw);
        String budgetId = trimmedOrNull(budgetRaw);
        String budgetCategoryId = trimmedOrNull(budgetCategoryRaw);
        if (budgetId != null) {
            String err = budgetLinkError(uid, budgetId);
            if (err != null) {
                throw new ApiException(HttpStatus.FORBIDDEN, fieldError("budget_id", err));
            }
        }
        String txnCurrency = currency == null || currency.isEmpty() ? "USD" : currency;
        String noteText = note == null ? "" : note.strip();
        LocalDate txnDate = date;
        Account acc = resolveAccount(accounts, uid, accountId);

        ScheduleLine paidLine = null;
        if (commitmentId != null) {
            String cid = commitmentId;
            Commitment c = commitments.get(cid).filter(x -> uid.equals(x.userId))
                    .orElseThrow(() -> ApiException.field("commitment_id", "Commitment not found."));
            CommitmentScheduleService.Progress progress = schedules.progress(c);
            if (scheduleLineId != null) {
                String lid = scheduleLineId;
                paidLine = progress.lines().stream()
                        .filter(l -> lid.equals(l.id) && ScheduleLine.OUTSTANDING.equals(l.status)).findFirst().orElse(null);
            }
            if (paidLine == null) {
                paidLine = progress.lines().stream().filter(l -> ScheduleLine.OUTSTANDING.equals(l.status)).findFirst().orElse(null);
            }
            if (paidLine == null) {
                throw ApiException.field("commitment_id", "No outstanding payment on this commitment.");
            }
            amount = paidLine.amount;
            scheduleLineId = paidLine.id;
            direction = "expense";
            if (description.isEmpty() || "unassigned".equalsIgnoreCase(description)) {
                description = c.name;
            }
            if (noteText.isEmpty()) {
                noteText = "Commitment payment — " + c.name;
            }
            txnCurrency = c.currency == null || c.currency.isEmpty() ? txnCurrency : c.currency;
        }

        if ("income".equals(direction)) {
            categoryId = null;
            commitmentId = null;
            scheduleLineId = null;
            if (description.strip().isEmpty()) {
                throw ApiException.field("description", "Enter what this income is (e.g. Salary).");
            }
        } else {
            if (categoryId != null) {
                categoryId = requireSubcategory(uid, categoryId).id;
            }
            if (commitmentId == null && categoryId == null && !description.isEmpty()) {
                categoryId = reports.suggestCategory(description, uid).map(c -> c.id).orElse(null);
            }
        }

        String extId = "";
        if (scheduleLineId != null) {
            extId = CommitmentScheduleService.lineExternalId(scheduleLineId);
            if (transactions.existsByUserIdAndExternalId(uid, extId)) {
                throw new ApiException(HttpStatus.CONFLICT,
                        fieldError("commitment_id", "This installment was already recorded as a transaction."));
            }
        }

        Transaction t = new Transaction();
        t.userId = uid;
        t.date = txnDate;
        t.month = ReportService.monthStr(txnDate);
        t.description = description.length() > 500 ? description.substring(0, 500) : description;
        t.categoryId = categoryId;
        t.classification = null;
        t.amount = amount;
        t.currency = txnCurrency;
        t.note = noteText;
        String tm = time == null || time.isEmpty() ? java.time.LocalTime.now().format(java.time.format.DateTimeFormatter.ofPattern("HH:mm")) : time;
        t.time = tm.length() > 8 ? tm.substring(0, 8) : tm;
        t.direction = direction;
        t.sourceAccount = acc.name;
        t.incomeSourceId = acc.id;
        t.commitmentId = commitmentId == null ? "" : commitmentId;
        t.scheduleLineId = scheduleLineId == null ? "" : scheduleLineId;
        t.externalId = extId;
        t.includeInUtilization = include;
        t.budgetId = budgetId == null ? "" : budgetId;
        t.budgetCategoryId = budgetCategoryId == null ? "" : budgetCategoryId;
        transactions.save(t);
        if (paidLine != null) {
            schedules.markPaid(paidLine, txnDate);
        }
        if (!"transfer".equals(direction)) {
            alerts.trigger(uid, t.date.getYear(), t.date.getMonthValue());
        }
        return ResponseEntity.status(HttpStatus.CREATED).body(transaction(t));
    }

    @GetMapping("/{pk}/")
    Map<String, Object> get(@PathVariable String pk) {
        return transaction(accessible(FinanceJson.uid(), pk).orElseThrow(ApiException::notFound));
    }

    private static String rawStr(Object v) {
        return v == null ? null : Py.str(v);
    }

    @PatchMapping("/{pk}/")
    Map<String, Object> update(@PathVariable String pk, @RequestBody(required = false) Map<String, Object> body) {
        String uid = FinanceJson.uid();
        Transaction t = accessible(uid, pk).orElseThrow(ApiException::notFound);
        Map<String, Object> data = body == null ? Map.of() : body;
        for (String field : List.of("date", "time", "description", "category_id", "classification", "amount", "currency",
                "note", "direction", "source_account", "account_id", "income_source_id", "budget_id", "budget_category_id")) {
            if (!data.containsKey(field)) {
                continue;
            }
            Object val = data.get(field);
            switch (field) {
                case "budget_id" -> t.budgetId = Py.truthy(val) ? Py.str(val).strip() : "";
                case "budget_category_id" -> t.budgetCategoryId = Py.truthy(val) ? Py.str(val).strip() : "";
                case "account_id", "income_source_id" -> {
                    String v = Py.truthy(val) ? Py.str(val).strip() : "";
                    if (!v.isEmpty()) {
                        Account acc = resolveAccount(accounts, uid, v);
                        t.incomeSourceId = acc.id;
                        t.sourceAccount = acc.name;
                    }
                }
                case "date" -> {
                    if (val instanceof String s) {
                        try {
                            t.date = LocalDate.parse(s.length() > 10 ? s.substring(0, 10) : s);
                        } catch (RuntimeException e) {
                            throw ApiException.field("date", "Date has wrong format. Use one of these formats instead: YYYY-MM-DD.");
                        }
                    } else {
                        t.date = null;
                    }
                }
                case "category_id" -> t.categoryId = "".equals(val) ? null : rawStr(val);
                case "amount" -> {
                    try {
                        t.amount = new BigDecimal(Py.str(val).strip());
                    } catch (RuntimeException e) {
                        throw ApiException.field("amount", "A valid number is required.");
                    }
                }
                case "time" -> {
                    String s = Py.truthy(val) ? Py.str(val) : "";
                    t.time = s.length() > 8 ? s.substring(0, 8) : s;
                }
                case "note" -> t.note = Py.truthy(val) ? Py.str(val) : "";
                case "currency" -> t.currency = Py.truthy(val) ? Py.str(val) : "USD";
                case "description" -> t.description = val == null ? "" : Py.str(val);
                case "classification" -> t.classification = rawStr(val);
                case "direction" -> t.direction = val == null ? "" : Py.str(val);
                case "source_account" -> t.sourceAccount = val == null ? "" : Py.str(val);
                default -> { }
            }
        }
        if ("income".equals(t.direction)) {
            t.categoryId = null;
            if (t.description == null || t.description.strip().isEmpty()) {
                throw ApiException.field("description", "Enter what this income is (e.g. Salary).");
            }
        } else if (t.categoryId != null && !t.categoryId.isEmpty() && data.containsKey("category_id")) {
            // A shared-budget editor may keep the owner's category without seeing it.
            t.categoryId = requireSubcategory(uid, t.categoryId).id;
        }
        if (t.budgetId != null && !t.budgetId.strip().isEmpty()) {
            String err = budgetLinkError(uid, t.budgetId);
            if (err != null) {
                throw new ApiException(HttpStatus.FORBIDDEN, fieldError("budget_id", err));
            }
        }
        if (t.date != null) {
            t.month = ReportService.monthStr(t.date);
        }
        transactions.save(t);
        alerts.trigger(uid, t.date == null ? null : t.date.getYear(), t.date == null ? null : t.date.getMonthValue());
        return transaction(t);
    }

    @DeleteMapping("/{pk}/")
    ResponseEntity<Void> delete(@PathVariable String pk) {
        String uid = FinanceJson.uid();
        Transaction t = accessible(uid, pk).orElseThrow(ApiException::notFound);
        Integer year = t.date == null ? null : t.date.getYear();
        Integer month = t.date == null ? null : t.date.getMonthValue();
        String lineId = t.scheduleLineId == null ? "" : t.scheduleLineId.strip();
        transactions.delete(t);
        if (!lineId.isEmpty()) {
            // The installment is no longer paid once its payment is deleted.
            scheduleLines.get(lineId).filter(l -> ScheduleLine.PAID.equals(l.status)).ifPresent(schedules::markOutstanding);
        }
        alerts.trigger(uid, year, month);
        return ResponseEntity.noContent().build();
    }

    // ---- Bulk actions: selected transactions and whole months ----

    static final int BULK_MAX_IDS = 1000;
    static final int BULK_MAX_MONTHS = 240;
    /** This port has no transaction status, so only the account and the merchant change in bulk. */
    private static final java.util.Set<String> BULK_UPDATE_FIELDS = java.util.Set.of("account_id", "category_id");

    static boolean isMonthKey(Object v) {
        if (!(v instanceof String s) || s.length() != 7 || s.charAt(4) != '-') {
            return false;
        }
        String y = s.substring(0, 4);
        String mo = s.substring(5);
        if (!y.chars().allMatch(Character::isDigit) || !mo.chars().allMatch(Character::isDigit)) {
            return false;
        }
        int m = Integer.parseInt(mo);
        return m >= 1 && m <= 12;
    }

    private static String rowMonth(Transaction t) {
        if (t.month != null && !t.month.isEmpty()) {
            return t.month;
        }
        return t.date == null ? "" : ReportService.monthStr(t.date);
    }

    /** Same rule as the web app's preserveDescriptionInNote: keep the bank text once in the note. */
    static String keepBankTextInNote(String description, String merchant, String note) {
        String desc = description == null ? "" : description.strip();
        String n = note == null ? "" : note.strip();
        String mer = merchant == null ? "" : merchant.strip();
        if (desc.isEmpty() || "Unassigned".equals(desc) || desc.equalsIgnoreCase(mer)) {
            return n;
        }
        if (n.isEmpty()) {
            return desc;
        }
        return n.contains(desc) ? n : desc + " · " + n;
    }

    /** Delete own rows: reopen paid installments, then refresh alerts once per month. */
    private int deleteRows(String uid, List<Transaction> rows) {
        TreeSet<String> months = new TreeSet<>();
        for (Transaction t : rows) {
            String lineId = t.scheduleLineId == null ? "" : t.scheduleLineId.strip();
            if (t.date != null) {
                months.add(ReportService.monthStr(t.date));
            }
            transactions.delete(t);
            if (!lineId.isEmpty()) {
                scheduleLines.get(lineId).filter(l -> ScheduleLine.PAID.equals(l.status)).ifPresent(schedules::markOutstanding);
            }
        }
        for (String ym : months) {
            alerts.trigger(uid, Integer.parseInt(ym.substring(0, 4)), Integer.parseInt(ym.substring(5)));
        }
        return rows.size();
    }

    /** Every month that has transactions, newest first, with counts and totals per currency. */
    @GetMapping("/months/")
    List<Map<String, Object>> months() {
        Map<String, Map<String, Object>> summary = new java.util.TreeMap<>(java.util.Comparator.reverseOrder());
        Map<String, Map<String, BigDecimal[]>> totals = new LinkedHashMap<>();
        for (Transaction t : transactions.findByUserIdOrderByIdAsc(FinanceJson.uid())) {
            String key = rowMonth(t);
            if (key.isEmpty()) {
                continue;
            }
            Map<String, Object> row = summary.computeIfAbsent(key, k -> {
                Map<String, Object> r = new LinkedHashMap<>();
                r.put("month", k);
                r.put("count", 0);
                r.put("income_count", 0);
                r.put("expense_count", 0);
                r.put("transfer_count", 0);
                r.put("first_date", null);
                r.put("last_date", null);
                return r;
            });
            String direction = List.of("income", "expense", "transfer").contains(t.direction) ? t.direction : "expense";
            row.merge("count", 1, (a, b) -> (Integer) a + (Integer) b);
            row.merge(direction + "_count", 1, (a, b) -> (Integer) a + (Integer) b);
            if (t.date != null) {
                String d = t.date.toString();
                Object first = row.get("first_date");
                Object last = row.get("last_date");
                if (first == null || d.compareTo((String) first) < 0) {
                    row.put("first_date", d);
                }
                if (last == null || d.compareTo((String) last) > 0) {
                    row.put("last_date", d);
                }
            }
            if (!"transfer".equals(direction)) {
                String cur = t.currency == null || t.currency.isEmpty() ? "USD" : t.currency;
                BigDecimal[] sums = totals.computeIfAbsent(key, k -> new java.util.TreeMap<>())
                        .computeIfAbsent(cur, c -> new BigDecimal[] {BigDecimal.ZERO, BigDecimal.ZERO});
                BigDecimal amount = t.amount == null ? BigDecimal.ZERO : t.amount.abs();
                int idx = "income".equals(direction) ? 0 : 1;
                sums[idx] = sums[idx].add(amount);
            }
        }
        List<Map<String, Object>> out = new ArrayList<>();
        summary.forEach((key, row) -> {
            List<Map<String, Object>> tot = new ArrayList<>();
            totals.getOrDefault(key, Map.of()).forEach((cur, sums) -> {
                Map<String, Object> r = new LinkedHashMap<>();
                r.put("currency", cur);
                r.put("income", sums[0].setScale(2, java.math.RoundingMode.HALF_EVEN).toPlainString());
                r.put("expense", sums[1].setScale(2, java.math.RoundingMode.HALF_EVEN).toPlainString());
                tot.add(r);
            });
            row.put("totals", tot);
            out.add(row);
        });
        return out;
    }

    /** Delete every transaction in the chosen months: {"months": ["2026-01", ...]}. */
    @PostMapping("/months/delete/")
    Map<String, Object> deleteMonths(@RequestBody(required = false) Map<String, Object> body) {
        Object raw = body == null ? null : body.get("months");
        if (!(raw instanceof List<?> months) || months.isEmpty()) {
            throw ApiException.field("months", "Choose at least one month.");
        }
        if (months.size() > BULK_MAX_MONTHS) {
            throw ApiException.field("months", "Choose at most " + BULK_MAX_MONTHS + " months at a time.");
        }
        for (Object m : months) {
            if (!isMonthKey(m)) {
                throw ApiException.field("months", "Use the YYYY-MM format (got " + Py.repr(Py.str(m)) + ").");
            }
        }
        TreeSet<String> wanted = new TreeSet<>();
        months.forEach(m -> wanted.add((String) m));
        String uid = FinanceJson.uid();
        List<Transaction> rows = transactions.findByUserIdOrderByIdAsc(uid).stream()
                .filter(t -> wanted.contains(rowMonth(t))).toList();
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("deleted", deleteRows(uid, rows));
        out.put("months", new ArrayList<>(wanted));
        return out;
    }

    /**
     * Act on several of the user's own transactions: {"ids": [...], "action": "delete"} or
     * {"ids": [...], "action": "update", "changes": {"account_id", "category_id"}}. A merchant only
     * applies to expenses that are not commitment payments; other rows count as skipped.
     */
    @PostMapping("/bulk/")
    Map<String, Object> bulk(@RequestBody(required = false) Map<String, Object> body) {
        Map<String, Object> data = body == null ? Map.of() : body;
        String uid = FinanceJson.uid();
        if (!(data.get("ids") instanceof List<?> ids) || ids.isEmpty()) {
            throw ApiException.field("ids", "Select at least one transaction.");
        }
        if (ids.size() > BULK_MAX_IDS) {
            throw ApiException.field("ids", "Select at most " + BULK_MAX_IDS + " transactions at a time.");
        }
        Object action = data.get("action");
        if (!"delete".equals(action) && !"update".equals(action)) {
            throw ApiException.field("action", "Use \"delete\" or \"update\".");
        }
        java.util.Set<String> wanted = new java.util.HashSet<>();
        ids.forEach(i -> wanted.add(Py.str(i)));
        List<Transaction> rows = transactions.findByUserIdOrderByIdAsc(uid).stream()
                .filter(t -> wanted.contains(t.id)).toList();
        int missing = wanted.size() - rows.size();
        if (rows.isEmpty()) {
            throw ApiException.notFound("None of the selected transactions were found.");
        }
        Map<String, Object> out = new LinkedHashMap<>();
        if ("delete".equals(action)) {
            out.put("deleted", deleteRows(uid, rows));
            out.put("missing", missing);
            return out;
        }

        if (!(data.get("changes") instanceof Map<?, ?> changes) || changes.isEmpty()) {
            throw ApiException.field("changes", "Choose what to change.");
        }
        List<String> unknown = changes.keySet().stream().map(Py::str).filter(k -> !BULK_UPDATE_FIELDS.contains(k))
                .sorted().toList();
        if (!unknown.isEmpty()) {
            throw ApiException.field("changes", "Cannot change " + String.join(", ", unknown) + " in bulk.");
        }
        Account acc = changes.containsKey("account_id")
                ? resolveAccount(accounts, uid, Py.truthy(changes.get("account_id")) ? Py.str(changes.get("account_id")).strip() : "")
                : null;
        Category sub = null;
        if (changes.containsKey("category_id")) {
            String cid = Py.truthy(changes.get("category_id")) ? Py.str(changes.get("category_id")).strip() : "";
            if (cid.isEmpty()) {
                throw ApiException.field("category_id", "Pick a merchant (subcategory).");
            }
            sub = requireSubcategory(uid, cid);
        }

        int updated = 0;
        int skipped = 0;
        TreeSet<String> months = new TreeSet<>();
        for (Transaction t : rows) {
            boolean changed = false;
            if (acc != null && !acc.id.equals(t.incomeSourceId)) {
                t.incomeSourceId = acc.id;
                t.sourceAccount = acc.name;
                changed = true;
            }
            boolean isPayment = t.commitmentId != null && !t.commitmentId.isEmpty();
            if (sub != null && "expense".equals(t.direction) && !isPayment && !sub.id.equals(t.categoryId)) {
                t.note = keepBankTextInNote(t.description, sub.name, t.note);
                t.description = sub.name.length() > 500 ? sub.name.substring(0, 500) : sub.name;
                t.categoryId = sub.id;
                changed = true;
            }
            if (!changed) {
                skipped++;
                continue;
            }
            transactions.save(t);
            updated++;
            if (t.date != null && !"transfer".equals(t.direction)) {
                months.add(ReportService.monthStr(t.date));
            }
        }
        for (String ym : months) {
            alerts.trigger(uid, Integer.parseInt(ym.substring(0, 4)), Integer.parseInt(ym.substring(5)));
        }
        out.put("updated", updated);
        out.put("skipped", skipped);
        out.put("missing", missing);
        return out;
    }

    /**
     * Import a bank statement (.csv / .xlsx / .json / .pdf). Positive amounts are income, negative
     * are expenses (or Debit/Credit columns). Re-uploading the same file adds nothing. A
     * password-protected PDF needs the "password" field (used once, never stored); without it the
     * answer is 400 with code password_required (or password_incorrect).
     */
    @PostMapping(value = "/upload/", consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
    Map<String, Object> upload(@RequestParam(required = false) MultipartFile file,
            @RequestParam Map<String, String> form) throws IOException {
        String uid = FinanceJson.uid();
        if (file == null || file.getOriginalFilename() == null || file.getOriginalFilename().isEmpty()) {
            throw ApiException.badRequest("Choose a .csv, .xlsx, .json or .pdf file.");
        }
        long maxBytes = props.getImportLimits().getMaxBytes();
        if (file.getSize() > 0 && file.getSize() > maxBytes) {
            throw ApiException.badRequest("File is too large (max " + maxBytes / (1024 * 1024) + " MB).");
        }
        UserLocale prefs = users.locale(uid);
        String currencyRaw = form.get("currency");
        String currency = (currencyRaw != null && !currencyRaw.isEmpty() ? currencyRaw
                : prefs.defaultCurrency() != null && !prefs.defaultCurrency().isEmpty() ? prefs.defaultCurrency() : "USD")
                .strip().toUpperCase();
        if (!LocaleConstants.VALID_CURRENCIES.contains(currency)) {
            throw ApiException.field("currency", "Unsupported currency.");
        }
        String dateFormat = (form.get("date_format") == null || form.get("date_format").isEmpty() ? "auto"
                : form.get("date_format")).strip().toLowerCase();
        if (!StatementImporter.DATE_FORMATS.contains(dateFormat)) {
            throw ApiException.field("date_format", "Use one of: " + String.join(", ", StatementImporter.DATE_FORMATS) + ".");
        }
        Account acc = null;
        Map<String, Object> formObj = new LinkedHashMap<>(form);
        String accountId = parseAccountId(formObj);
        if (!accountId.isEmpty()) {
            acc = resolveAccount(accounts, uid, accountId);
        }

        List<List<String>> rows;
        int uncertain;
        try {
            StatementFormats.Parsed parsed = StatementImporter.readStatement(file.getOriginalFilename(), file.getBytes(),
                    form.getOrDefault("password", ""));
            rows = parsed.rows();
            uncertain = parsed.uncertain();
        } catch (StatementFormats.PasswordError e) {
            Map<String, Object> body = new LinkedHashMap<>();
            body.put("detail", e.getMessage());
            body.put("code", e.code());
            throw new ApiException(HttpStatus.BAD_REQUEST, body);
        } catch (StatementImporter.ImportError e) {
            throw ApiException.badRequest(e.getMessage());
        }
        int maxRows = props.getImportLimits().getMaxRows();
        if (rows.size() > maxRows + 1) {
            throw ApiException.badRequest("Too many rows (max " + maxRows + "). Split the file.");
        }
        Map<String, Integer> colMap = rows.isEmpty() ? null : StatementImporter.columnMap(rows.get(0));
        List<List<String>> dataRows = colMap != null ? rows.subList(1, rows.size()) : rows;
        if ("auto".equals(dateFormat)) {
            String fallback = StatementImporter.defaultDateFormat(prefs.country());
            int dateIdx = colMap != null ? colMap.get("date") : 0;
            List<String> dates = new ArrayList<>();
            for (List<String> r : dataRows) {
                if (r.size() > dateIdx) {
                    dates.add(r.get(dateIdx));
                }
            }
            dateFormat = StatementImporter.guessDateFormat(dates, fallback);
        }

        int created = 0;
        int skipped = 0;
        int matched = 0;
        List<Map<String, Object>> errors = new ArrayList<>();
        Map<String, Map<String, Object>> unmatchedMap = new LinkedHashMap<>();
        TreeSet<String> monthsTouched = new TreeSet<>();
        Map<String, Integer> occurrences = new LinkedHashMap<>();
        int rowNo = colMap != null ? 2 : 1;
        for (List<String> row : dataRows) {
            int currentRow = rowNo++;
            if (row.stream().allMatch(c -> c == null || c.strip().isEmpty())) {
                continue;
            }
            StatementImporter.Fields f;
            try {
                f = StatementImporter.extractFields(row, colMap);
            } catch (IndexOutOfBoundsException | IllegalArgumentException e) {
                skipped++;
                errors.add(rowError(currentRow, "Missing date, description or amount."));
                continue;
            }
            if (StatementImporter.HEADER_ALIASES.get("date").contains(f.date().toLowerCase())) {
                continue;
            }
            LocalDate txnDate;
            BigDecimal amount;
            try {
                txnDate = StatementImporter.parseDate(f.date(), dateFormat);
                amount = StatementImporter.parseAmount(f.amount());
            } catch (IllegalArgumentException e) {
                skipped++;
                errors.add(rowError(currentRow, "Could not read date or amount: " + f.date() + " / " + f.amount()));
                continue;
            }
            String direction = amount.signum() > 0 ? "income" : "expense";
            amount = amount.abs();
            String desc = f.description();
            String base = StatementImporter.dedupeKey(txnDate, amount, desc, 1);
            int occurrence = occurrences.merge(base, 1, Integer::sum);
            String extId = StatementImporter.dedupeKey(txnDate, amount, desc, occurrence);
            if (transactions.existsByUserIdAndExternalId(uid, extId)) {
                skipped++;
                continue;
            }
            Optional<Category> cat = "expense".equals(direction) ? reports.suggestCategory(desc, uid) : Optional.empty();
            Transaction t = new Transaction();
            t.userId = uid;
            t.date = txnDate;
            t.month = ReportService.monthStr(txnDate);
            t.description = desc.length() > 500 ? desc.substring(0, 500) : desc;
            t.amount = amount;
            t.currency = currency;
            t.direction = direction;
            t.categoryId = cat.map(c -> c.id).orElse(null);
            t.externalId = extId;
            t.sourceAccount = acc != null ? acc.name : "";
            t.incomeSourceId = acc != null ? acc.id : "";
            transactions.save(t);
            created++;
            monthsTouched.add(String.format("%04d-%02d", txnDate.getYear(), txnDate.getMonthValue()));

            if ("expense".equals(direction)) {
                if (cat.isPresent()) {
                    matched++;
                } else {
                    String merchant = ReportService.merchantKey(desc);
                    String key = merchant.toLowerCase();
                    if (key.isEmpty()) {
                        continue;
                    }
                    Map<String, Object> bucket = unmatchedMap.get(key);
                    if (bucket == null) {
                        List<String> parts = new ArrayList<>();
                        for (String p : merchant.split("\\s+")) {
                            String noDots = p.replace(".", "");
                            if (!(!noDots.isEmpty() && noDots.chars().allMatch(Character::isDigit))) {
                                parts.add(p);
                            }
                        }
                        String suggestion = parts.isEmpty() ? merchant : String.join(" ", parts.subList(0, Math.min(3, parts.size())));
                        bucket = new LinkedHashMap<>();
                        bucket.put("merchant", merchant);
                        bucket.put("keyword_suggestion", suggestion.length() > 80 ? suggestion.substring(0, 80) : suggestion);
                        bucket.put("count", 0);
                        bucket.put("transaction_ids", new ArrayList<String>());
                        bucket.put("sample_descriptions", new ArrayList<String>());
                        unmatchedMap.put(key, bucket);
                    }
                    bucket.put("count", (int) bucket.get("count") + 1);
                    @SuppressWarnings("unchecked")
                    List<String> ids = (List<String>) bucket.get("transaction_ids");
                    ids.add(t.id);
                    @SuppressWarnings("unchecked")
                    List<String> samples = (List<String>) bucket.get("sample_descriptions");
                    if (samples.size() < 3 && !samples.contains(desc)) {
                        samples.add(desc.length() > 120 ? desc.substring(0, 120) : desc);
                    }
                }
            }
        }

        int alertEmailsSent = 0;
        if (created > 0) {
            for (String ym : monthsTouched) {
                alerts.refresh(uid, Integer.parseInt(ym.substring(0, 4)), Integer.parseInt(ym.substring(5, 7)), true);
            }
            alertEmailsSent = alerts.process(List.of(uid)).getOrDefault("emails_sent", 0);
        }
        List<Map<String, Object>> unmatched = new ArrayList<>(unmatchedMap.values());
        unmatched.sort((a, b) -> {
            int c = Integer.compare((int) b.get("count"), (int) a.get("count"));
            return c != 0 ? c : String.valueOf(a.get("merchant")).toLowerCase().compareTo(String.valueOf(b.get("merchant")).toLowerCase());
        });
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("created", created);
        out.put("skipped", skipped);
        out.put("matched", matched);
        out.put("unmatched_count", unmatched.size());
        out.put("unmatched", unmatched);
        out.put("alerts_emails_sent", alertEmailsSent);
        out.put("date_format", dateFormat);
        out.put("currency", currency);
        out.put("errors", errors.size() > 20 ? errors.subList(0, 20) : errors);
        // PDF lines with no balance or CR/DR marker were imported as money out: worth a check.
        out.put("uncertain_direction", uncertain);
        return out;
    }

    private static Map<String, Object> rowError(int row, String error) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("row", row);
        m.put("error", error);
        return m;
    }
}
