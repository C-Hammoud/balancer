package com.financetracker.finance.persistence.firestore;

import static com.financetracker.shared.datastore.FirestoreDocs.bool;
import static com.financetracker.shared.datastore.FirestoreDocs.date;
import static com.financetracker.shared.datastore.FirestoreDocs.decStr;
import static com.financetracker.shared.datastore.FirestoreDocs.decimal;
import static com.financetracker.shared.datastore.FirestoreDocs.instant;
import static com.financetracker.shared.datastore.FirestoreDocs.integer;
import static com.financetracker.shared.datastore.FirestoreDocs.isoDate;
import static com.financetracker.shared.datastore.FirestoreDocs.str;
import static com.financetracker.shared.datastore.FirestoreDocs.ts;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Repository;

import com.financetracker.finance.domain.Account;
import com.financetracker.finance.domain.Budget;
import com.financetracker.finance.domain.BudgetAlert;
import com.financetracker.finance.domain.BudgetPlan;
import com.financetracker.finance.domain.BudgetThreshold;
import com.financetracker.finance.domain.Category;
import com.financetracker.finance.domain.CategoryGroup;
import com.financetracker.finance.domain.Commitment;
import com.financetracker.finance.domain.FinanceRepositories;
import com.financetracker.finance.domain.FinancialStanding;
import com.financetracker.finance.domain.GroupBucket;
import com.financetracker.finance.domain.IncomeStream;
import com.financetracker.finance.domain.MerchantLink;
import com.financetracker.finance.domain.PersonalBudget;
import com.financetracker.finance.domain.PersonalBudgetCategory;
import com.financetracker.finance.domain.PersonalBudgetInvite;
import com.financetracker.finance.domain.PersonalBudgetMember;
import com.financetracker.finance.domain.PersonalBudgetNotification;
import com.financetracker.finance.domain.Savings;
import com.financetracker.finance.domain.ScheduleLine;
import com.financetracker.finance.domain.Transaction;
import com.financetracker.finance.domain.TypeCategoryMap;
import com.financetracker.shared.config.DataStoreType;
import com.financetracker.shared.datastore.ConditionalOnDataStore;
import com.financetracker.shared.datastore.FirestoreCrud;
import com.google.cloud.firestore.Firestore;

/**
 * Firestore adapters. Collection names and document fields are exactly those of the Django
 * Firestore models (budgeting/firestore_models.py, personal_budget_fs.py, planning_fs.py), so
 * existing production data is read and written unchanged.
 */
final class FirestoreFinanceRepositories {

    private FirestoreFinanceRepositories() {
    }

    /** data.get(key) as a string, None preserved. */
    static String raw(Map<String, Object> d, String key) {
        Object v = d == null ? null : d.get(key);
        return v == null ? null : String.valueOf(v);
    }

    /** int(data.get(key, dflt) or dflt) */
    static int intOr(Map<String, Object> d, String key, int dflt) {
        if (d == null || !d.containsKey(key) || d.get(key) == null) {
            return dflt;
        }
        int v = integer(d, key);
        return v == 0 ? dflt : v;
    }

    static String strOr(Map<String, Object> d, String key, String dflt) {
        String v = str(d, key);
        return v.isEmpty() ? dflt : v;
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class Groups extends FirestoreCrud<CategoryGroup> implements FinanceRepositories.GroupRepository {
        Groups(Firestore db) {
            super(db, "budgeting_groups");
        }

        @Override
        protected Map<String, Object> toDoc(CategoryGroup g) {
            Map<String, Object> d = new HashMap<>();
            d.put("name", g.name);
            d.put("order", g.order);
            d.put("user_id", g.userId == null ? "" : g.userId);
            return d;
        }

        @Override
        protected CategoryGroup fromDoc(String id, Map<String, Object> d) {
            CategoryGroup g = new CategoryGroup();
            g.name = str(d, "name");
            g.order = integer(d, "order");
            g.userId = str(d, "user_id");
            return g;
        }

        @Override
        public List<CategoryGroup> findAllByOrderByIdAsc() {
            return all();
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class Categories extends FirestoreCrud<Category> implements FinanceRepositories.CategoryRepository {
        Categories(Firestore db) {
            super(db, "budgeting_categories");
        }

        @Override
        protected Map<String, Object> toDoc(Category c) {
            Map<String, Object> d = new HashMap<>();
            d.put("name", c.name);
            d.put("group_id", c.groupId);
            d.put("include_in_reports", c.includeInReports);
            d.put("order", c.order);
            d.put("user_id", c.userId == null ? "" : c.userId);
            return d;
        }

        @Override
        protected Category fromDoc(String id, Map<String, Object> d) {
            Category c = new Category();
            c.name = str(d, "name");
            c.groupId = str(d, "group_id");
            c.includeInReports = bool(d, "include_in_reports", true);
            c.order = integer(d, "order");
            c.userId = str(d, "user_id");
            return c;
        }

        @Override
        public List<Category> findAllByOrderByIdAsc() {
            return all();
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class Transactions extends FirestoreCrud<Transaction> implements FinanceRepositories.TransactionRepository {
        Transactions(Firestore db) {
            super(db, "budgeting_transactions");
        }

        @Override
        protected Map<String, Object> toDoc(Transaction t) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", t.userId);
            d.put("date", isoDate(t.date));
            d.put("month", t.month);
            d.put("description", t.description == null ? "" : t.description);
            d.put("category_id", t.categoryId);
            d.put("classification", t.classification);
            d.put("amount", decStr(t.amount));
            d.put("direction", t.direction);
            d.put("currency", t.currency == null || t.currency.isEmpty() ? "USD" : t.currency);
            d.put("note", t.note == null ? "" : t.note);
            d.put("time", t.time == null ? "" : t.time);
            d.put("source_account", t.sourceAccount == null ? "" : t.sourceAccount);
            d.put("income_source_id", t.incomeSourceId == null ? "" : t.incomeSourceId);
            d.put("commitment_id", t.commitmentId == null ? "" : t.commitmentId);
            d.put("schedule_line_id", t.scheduleLineId == null ? "" : t.scheduleLineId);
            d.put("external_id", t.externalId == null ? "" : t.externalId);
            d.put("include_in_utilization", t.includeInUtilization);
            d.put("budget_id", t.budgetId == null ? "" : t.budgetId);
            d.put("budget_category_id", t.budgetCategoryId == null ? "" : t.budgetCategoryId);
            d.put("created_at", ts(t.createdAt));
            d.put("updated_at", ts(t.updatedAt));
            return d;
        }

        @Override
        protected Transaction fromDoc(String id, Map<String, Object> d) {
            Transaction t = new Transaction();
            t.userId = str(d, "user_id");
            t.date = date(d, "date");
            t.month = str(d, "month");
            t.description = str(d, "description");
            t.categoryId = raw(d, "category_id");
            t.classification = raw(d, "classification");
            t.amount = decimal(d, "amount");
            t.direction = d.containsKey("direction") ? raw(d, "direction") : "expense";
            t.currency = strOr(d, "currency", "USD");
            t.note = str(d, "note");
            String time = str(d, "time");
            t.time = time.length() > 8 ? time.substring(0, 8) : time;
            t.sourceAccount = str(d, "source_account");
            t.incomeSourceId = str(d, "income_source_id");
            t.commitmentId = str(d, "commitment_id");
            t.scheduleLineId = str(d, "schedule_line_id");
            t.externalId = str(d, "external_id");
            t.includeInUtilization = bool(d, "include_in_utilization", false);
            t.budgetId = str(d, "budget_id");
            t.budgetCategoryId = str(d, "budget_category_id");
            t.createdAt = instant(d, "created_at");
            t.updatedAt = instant(d, "updated_at");
            return t;
        }

        @Override
        public List<Transaction> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }

        @Override
        public List<Transaction> findByUserIdAndMonthOrderByIdAsc(String userId, String month) {
            return where("user_id", userId, "month", month);
        }

        @Override
        public List<Transaction> findByBudgetIdOrderByIdAsc(String budgetId) {
            return where("budget_id", budgetId);
        }

        @Override
        public boolean existsByUserIdAndExternalId(String userId, String externalId) {
            return exists("user_id", userId, "external_id", externalId);
        }

        @Override
        public Optional<Transaction> findFirstByUserIdAndExternalIdOrderByIdAsc(String userId, String externalId) {
            return where("user_id", userId, "external_id", externalId).stream().findFirst();
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class MerchantLinks extends FirestoreCrud<MerchantLink> implements FinanceRepositories.MerchantLinkRepository {
        MerchantLinks(Firestore db) {
            super(db, "budgeting_merchant_links");
        }

        @Override
        protected Map<String, Object> toDoc(MerchantLink l) {
            Map<String, Object> d = new HashMap<>();
            d.put("keyword", l.keyword);
            d.put("category_id", l.categoryId);
            d.put("user_id", l.userId);
            return d;
        }

        @Override
        protected MerchantLink fromDoc(String id, Map<String, Object> d) {
            MerchantLink l = new MerchantLink();
            l.keyword = str(d, "keyword");
            l.categoryId = str(d, "category_id");
            l.userId = raw(d, "user_id");
            return l;
        }

        @Override
        public List<MerchantLink> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }

        @Override
        public List<MerchantLink> findAllByOrderByIdAsc() {
            return all();
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class Budgets extends FirestoreCrud<Budget> implements FinanceRepositories.BudgetRepository {
        Budgets(Firestore db) {
            super(db, "budgeting_budgets");
        }

        @Override
        protected Map<String, Object> toDoc(Budget b) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", b.userId);
            d.put("category_id", b.categoryId == null ? "" : b.categoryId);
            d.put("group_id", b.groupId == null ? "" : b.groupId);
            d.put("year", b.year);
            d.put("month", b.month);
            d.put("forecast", decStr(b.forecast));
            return d;
        }

        @Override
        protected Budget fromDoc(String id, Map<String, Object> d) {
            Budget b = new Budget();
            b.userId = str(d, "user_id");
            b.categoryId = str(d, "category_id");
            b.groupId = str(d, "group_id");
            b.year = integer(d, "year");
            b.month = integer(d, "month");
            b.forecast = decimal(d, "forecast");
            return b;
        }

        @Override
        public List<Budget> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }

        @Override
        public List<Budget> findByUserIdAndYearOrderByIdAsc(String userId, int year) {
            return where("user_id", userId, "year", year);
        }

        @Override
        public List<Budget> findByUserIdAndYearAndMonthOrderByIdAsc(String userId, int year, int month) {
            return where("user_id", userId, "year", year, "month", month);
        }

        @Override
        public List<Budget> findByUserIdAndGroupIdAndYearAndMonthOrderByIdAsc(String userId, String groupId, int year, int month) {
            return where("user_id", userId, "group_id", groupId, "year", year, "month", month);
        }

        @Override
        public List<Budget> findByUserIdAndCategoryIdAndYearAndMonthOrderByIdAsc(String userId, String categoryId, int year, int month) {
            return where("user_id", userId, "category_id", categoryId, "year", year, "month", month);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class SavingsAdapter extends FirestoreCrud<Savings> implements FinanceRepositories.SavingsRepository {
        SavingsAdapter(Firestore db) {
            super(db, "budgeting_savings");
        }

        @Override
        protected Map<String, Object> toDoc(Savings s) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", s.userId);
            d.put("year", s.year);
            d.put("month", s.month);
            d.put("actual", s.actual == null ? null : decStr(s.actual));
            d.put("target", decStr(s.target));
            d.put("goal_status", s.goalStatus);
            return d;
        }

        @Override
        protected Savings fromDoc(String id, Map<String, Object> d) {
            Savings s = new Savings();
            s.userId = str(d, "user_id");
            s.year = integer(d, "year");
            s.month = integer(d, "month");
            s.actual = d.get("actual") == null ? null : decimal(d, "actual");
            s.target = decimal(d, "target");
            s.goalStatus = strOr(d, "goal_status", "pending");
            return s;
        }

        @Override
        public List<Savings> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }

        @Override
        public Optional<Savings> findFirstByUserIdAndYearAndMonthOrderByIdAsc(String userId, int year, int month) {
            return where("user_id", userId, "year", year, "month", month).stream().findFirst();
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class Commitments extends FirestoreCrud<Commitment> implements FinanceRepositories.CommitmentRepository {
        Commitments(Firestore db) {
            super(db, "budgeting_commitments");
        }

        @Override
        protected Map<String, Object> toDoc(Commitment c) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", c.userId);
            d.put("name", c.name);
            d.put("amount", decStr(c.amount));
            d.put("start_date", isoDate(c.startDate));
            d.put("term_months", c.termMonths);
            d.put("frequency", c.frequency);
            d.put("payment_amount", decStr(c.paymentAmount));
            d.put("balloon", decStr(c.balloon));
            d.put("currency", c.currency == null || c.currency.isEmpty() ? "USD" : c.currency);
            d.put("reminder_enabled", c.reminderEnabled);
            d.put("reminder_days_before", c.reminderDaysBefore);
            d.put("created_at", ts(c.createdAt));
            d.put("updated_at", ts(c.updatedAt));
            return d;
        }

        @Override
        protected Commitment fromDoc(String id, Map<String, Object> d) {
            Commitment c = new Commitment();
            c.userId = str(d, "user_id");
            c.name = str(d, "name");
            c.amount = decimal(d, "amount");
            c.startDate = date(d, "start_date");
            c.termMonths = integer(d, "term_months");
            c.frequency = strOr(d, "frequency", "monthly");
            c.paymentAmount = decimal(d, "payment_amount");
            c.balloon = decimal(d, "balloon");
            c.currency = strOr(d, "currency", "USD");
            c.reminderEnabled = bool(d, "reminder_enabled", true);
            c.reminderDaysBefore = intOr(d, "reminder_days_before", 3);
            c.createdAt = instant(d, "created_at");
            c.updatedAt = instant(d, "updated_at");
            return c;
        }

        @Override
        public List<Commitment> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class ScheduleLines extends FirestoreCrud<ScheduleLine> implements FinanceRepositories.ScheduleLineRepository {
        ScheduleLines(Firestore db) {
            super(db, "budgeting_commitment_schedule_lines");
        }

        @Override
        protected Map<String, Object> toDoc(ScheduleLine l) {
            Map<String, Object> d = new HashMap<>();
            d.put("commitment_id", l.commitmentId);
            d.put("due_date", isoDate(l.dueDate));
            d.put("amount", decStr(l.amount));
            d.put("status", l.status);
            d.put("sequence", l.sequence);
            d.put("paid_date", isoDate(l.paidDate));
            d.put("reminder_sent", l.reminderSent);
            return d;
        }

        @Override
        protected ScheduleLine fromDoc(String id, Map<String, Object> d) {
            ScheduleLine l = new ScheduleLine();
            l.commitmentId = str(d, "commitment_id");
            l.dueDate = date(d, "due_date");
            l.amount = decimal(d, "amount");
            l.status = strOr(d, "status", ScheduleLine.OUTSTANDING);
            l.sequence = integer(d, "sequence");
            l.paidDate = date(d, "paid_date");
            l.reminderSent = bool(d, "reminder_sent", false);
            return l;
        }

        @Override
        public List<ScheduleLine> findByCommitmentIdOrderByIdAsc(String commitmentId) {
            return where("commitment_id", commitmentId);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class Standings extends FirestoreCrud<FinancialStanding> implements FinanceRepositories.FinancialStandingRepository {
        Standings(Firestore db) {
            super(db, "budgeting_financial_standings");
        }

        @Override
        protected Map<String, Object> toDoc(FinancialStanding s) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", s.userId);
            d.put("snapshot_date", isoDate(s.snapshotDate));
            d.put("total_assets", decStr(s.totalAssets));
            d.put("current_assets", decStr(s.currentAssets));
            d.put("fixed_assets", decStr(s.fixedAssets));
            d.put("total_liabilities", decStr(s.totalLiabilities));
            d.put("short_term_liabilities", decStr(s.shortTermLiabilities));
            d.put("long_term_liabilities", decStr(s.longTermLiabilities));
            d.put("notes", s.notes == null ? "" : s.notes);
            d.put("created_at", ts(s.createdAt));
            return d;
        }

        @Override
        protected FinancialStanding fromDoc(String id, Map<String, Object> d) {
            FinancialStanding s = new FinancialStanding();
            s.userId = str(d, "user_id");
            s.snapshotDate = date(d, "snapshot_date");
            s.totalAssets = decimal(d, "total_assets");
            s.currentAssets = decimal(d, "current_assets");
            s.fixedAssets = decimal(d, "fixed_assets");
            s.totalLiabilities = decimal(d, "total_liabilities");
            s.shortTermLiabilities = decimal(d, "short_term_liabilities");
            s.longTermLiabilities = decimal(d, "long_term_liabilities");
            s.notes = str(d, "notes");
            s.createdAt = instant(d, "created_at");
            return s;
        }

        @Override
        public List<FinancialStanding> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class TypeMaps extends FirestoreCrud<TypeCategoryMap> implements FinanceRepositories.TypeCategoryMapRepository {
        TypeMaps(Firestore db) {
            super(db, "budgeting_type_category_maps");
        }

        @Override
        protected Map<String, Object> toDoc(TypeCategoryMap m) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", m.userId);
            d.put("consumption_type", m.consumptionType);
            d.put("category_id", m.categoryId);
            return d;
        }

        @Override
        protected TypeCategoryMap fromDoc(String id, Map<String, Object> d) {
            TypeCategoryMap m = new TypeCategoryMap();
            m.userId = raw(d, "user_id");
            m.consumptionType = strOr(d, "consumption_type", "other").toLowerCase(Locale.ROOT);
            m.categoryId = str(d, "category_id");
            return m;
        }

        @Override
        public List<TypeCategoryMap> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }

        @Override
        public List<TypeCategoryMap> findAllByOrderByIdAsc() {
            return all();
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class Thresholds extends FirestoreCrud<BudgetThreshold> implements FinanceRepositories.BudgetThresholdRepository {
        Thresholds(Firestore db) {
            super(db, "budgeting_thresholds");
        }

        @Override
        protected Map<String, Object> toDoc(BudgetThreshold t) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", t.userId);
            d.put("category_id", t.categoryId == null ? "" : t.categoryId);
            d.put("warn_pct", decStr(t.warnPct));
            d.put("critical_pct", decStr(t.criticalPct));
            d.put("email_enabled", t.emailEnabled);
            return d;
        }

        @Override
        protected BudgetThreshold fromDoc(String id, Map<String, Object> d) {
            BudgetThreshold t = new BudgetThreshold();
            t.userId = str(d, "user_id");
            String cid = str(d, "category_id");
            t.categoryId = cid.isEmpty() ? null : cid;
            t.warnPct = d.containsKey("warn_pct") ? decimal(d, "warn_pct") : new java.math.BigDecimal("80");
            t.criticalPct = d.containsKey("critical_pct") ? decimal(d, "critical_pct") : new java.math.BigDecimal("100");
            t.emailEnabled = bool(d, "email_enabled", true);
            return t;
        }

        @Override
        public List<BudgetThreshold> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class Accounts extends FirestoreCrud<Account> implements FinanceRepositories.AccountRepository {
        Accounts(Firestore db) {
            super(db, "budgeting_income_sources");
        }

        @Override
        protected Map<String, Object> toDoc(Account a) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", a.userId);
            d.put("name", a.name);
            d.put("account_type", a.accountType == null || a.accountType.isEmpty() ? "bank" : a.accountType);
            d.put("order", a.order);
            d.put("is_active", a.active);
            d.put("is_default_for_expenses", a.defaultForExpenses);
            return d;
        }

        @Override
        protected Account fromDoc(String id, Map<String, Object> d) {
            Account a = new Account();
            a.userId = str(d, "user_id");
            a.name = str(d, "name");
            a.accountType = strOr(d, "account_type", "bank");
            a.order = integer(d, "order");
            a.active = bool(d, "is_active", true);
            a.defaultForExpenses = bool(d, "is_default_for_expenses", false);
            return a;
        }

        @Override
        public List<Account> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class Alerts extends FirestoreCrud<BudgetAlert> implements FinanceRepositories.BudgetAlertRepository {
        Alerts(Firestore db) {
            super(db, "budgeting_alerts");
        }

        @Override
        protected Map<String, Object> toDoc(BudgetAlert a) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", a.userId);
            d.put("year", a.year);
            d.put("month", a.month);
            d.put("category_id", a.categoryId == null ? "" : a.categoryId);
            d.put("severity", a.severity);
            d.put("title", a.title);
            d.put("description", a.description);
            d.put("alert_type", a.alertType == null || a.alertType.isEmpty() ? "utilization" : a.alertType);
            d.put("utilization_pct", a.utilizationPct == null ? null : decStr(a.utilizationPct));
            d.put("actual", decStr(a.actual));
            d.put("forecast", decStr(a.forecast));
            d.put("commitment_id", a.commitmentId == null ? "" : a.commitmentId);
            d.put("schedule_line_id", a.scheduleLineId == null ? "" : a.scheduleLineId);
            d.put("due_date", a.dueDate == null ? "" : a.dueDate);
            d.put("commitment_name", a.commitmentName == null ? "" : a.commitmentName);
            d.put("is_resolved", a.isResolved);
            d.put("resolution", a.resolution == null ? "" : a.resolution);
            d.put("resolved_at", ts(a.resolvedAt));
            d.put("snoozed_until", ts(a.snoozedUntil));
            d.put("email_sent", a.emailSent);
            d.put("fingerprint", a.fingerprint);
            d.put("created_at", ts(a.createdAt));
            d.put("updated_at", ts(a.updatedAt));
            return d;
        }

        @Override
        protected BudgetAlert fromDoc(String id, Map<String, Object> d) {
            BudgetAlert a = new BudgetAlert();
            a.userId = str(d, "user_id");
            a.year = integer(d, "year");
            a.month = integer(d, "month");
            a.categoryId = str(d, "category_id");
            a.severity = strOr(d, "severity", "WARN");
            a.title = str(d, "title");
            a.description = str(d, "description");
            String type = str(d, "alert_type");
            a.alertType = !type.isEmpty() ? type : a.categoryId.startsWith("commitment:") ? "commitment_due" : "utilization";
            a.utilizationPct = d.get("utilization_pct") == null ? null : decimal(d, "utilization_pct");
            a.actual = decimal(d, "actual");
            a.forecast = decimal(d, "forecast");
            a.commitmentId = str(d, "commitment_id");
            a.scheduleLineId = str(d, "schedule_line_id");
            a.dueDate = str(d, "due_date");
            a.commitmentName = str(d, "commitment_name");
            a.isResolved = bool(d, "is_resolved", false);
            a.resolution = str(d, "resolution");
            a.resolvedAt = instant(d, "resolved_at");
            a.snoozedUntil = instant(d, "snoozed_until");
            a.emailSent = bool(d, "email_sent", false);
            a.fingerprint = str(d, "fingerprint");
            a.createdAt = instant(d, "created_at");
            a.updatedAt = instant(d, "updated_at");
            return a;
        }

        @Override
        public List<BudgetAlert> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class PersonalBudgets extends FirestoreCrud<PersonalBudget> implements FinanceRepositories.PersonalBudgetRepository {
        PersonalBudgets(Firestore db) {
            super(db, "budgeting_personal_budgets");
        }

        @Override
        protected Map<String, Object> toDoc(PersonalBudget b) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", b.userId);
            d.put("name", b.name);
            d.put("description", b.description == null ? "" : b.description);
            d.put("currency", b.currency == null || b.currency.isEmpty() ? "USD" : b.currency);
            d.put("start_date", isoDate(b.startDate));
            d.put("end_date", isoDate(b.endDate));
            d.put("total_amount", decStr(b.totalAmount));
            d.put("status", b.status == null || b.status.isEmpty() ? PersonalBudget.DRAFT : b.status);
            d.put("project_tag", b.projectTag == null ? "" : b.projectTag);
            d.put("notes", b.notes == null ? "" : b.notes);
            d.put("is_default", b.isDefault);
            d.put("created_at", ts(b.createdAt));
            d.put("updated_at", ts(b.updatedAt));
            return d;
        }

        @Override
        protected PersonalBudget fromDoc(String id, Map<String, Object> d) {
            PersonalBudget b = new PersonalBudget();
            b.userId = str(d, "user_id");
            b.name = str(d, "name");
            b.description = str(d, "description");
            b.currency = strOr(d, "currency", "USD");
            b.startDate = date(d, "start_date");
            b.endDate = date(d, "end_date");
            b.totalAmount = decimal(d, "total_amount");
            b.status = strOr(d, "status", PersonalBudget.DRAFT);
            b.projectTag = str(d, "project_tag");
            b.notes = str(d, "notes");
            b.isDefault = bool(d, "is_default", false);
            b.createdAt = instant(d, "created_at");
            b.updatedAt = instant(d, "updated_at");
            return b;
        }

        @Override
        public List<PersonalBudget> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class PersonalBudgetCategories extends FirestoreCrud<PersonalBudgetCategory>
            implements FinanceRepositories.PersonalBudgetCategoryRepository {
        PersonalBudgetCategories(Firestore db) {
            super(db, "budgeting_personal_budget_categories");
        }

        @Override
        protected Map<String, Object> toDoc(PersonalBudgetCategory c) {
            Map<String, Object> d = new HashMap<>();
            d.put("budget_id", c.budgetId);
            d.put("name", c.name);
            d.put("allocated_amount", decStr(c.allocatedAmount));
            d.put("order", c.order);
            d.put("notes", c.notes == null ? "" : c.notes);
            d.put("group_id", c.groupId == null ? "" : c.groupId);
            d.put("category_id", c.categoryId == null ? "" : c.categoryId);
            d.put("parent_id", c.parentId == null ? "" : c.parentId);
            return d;
        }

        @Override
        protected PersonalBudgetCategory fromDoc(String id, Map<String, Object> d) {
            PersonalBudgetCategory c = new PersonalBudgetCategory();
            c.budgetId = str(d, "budget_id");
            c.name = str(d, "name");
            c.allocatedAmount = decimal(d, "allocated_amount");
            c.order = integer(d, "order");
            c.notes = str(d, "notes");
            c.groupId = str(d, "group_id");
            c.categoryId = str(d, "category_id");
            c.parentId = str(d, "parent_id");
            return c;
        }

        @Override
        public List<PersonalBudgetCategory> findByBudgetIdOrderByIdAsc(String budgetId) {
            return where("budget_id", budgetId);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class PersonalBudgetMembers extends FirestoreCrud<PersonalBudgetMember>
            implements FinanceRepositories.PersonalBudgetMemberRepository {
        PersonalBudgetMembers(Firestore db) {
            super(db, "budgeting_personal_budget_members");
        }

        @Override
        protected Map<String, Object> toDoc(PersonalBudgetMember m) {
            Map<String, Object> d = new HashMap<>();
            d.put("budget_id", m.budgetId);
            d.put("user_id", m.userId);
            d.put("role", m.role == null || m.role.isEmpty() ? PersonalBudgetMember.VIEWER : m.role);
            d.put("created_at", ts(m.createdAt));
            d.put("updated_at", ts(m.updatedAt));
            return d;
        }

        @Override
        protected PersonalBudgetMember fromDoc(String id, Map<String, Object> d) {
            PersonalBudgetMember m = new PersonalBudgetMember();
            m.budgetId = str(d, "budget_id");
            m.userId = str(d, "user_id");
            m.role = strOr(d, "role", PersonalBudgetMember.VIEWER);
            m.createdAt = instant(d, "created_at");
            m.updatedAt = instant(d, "updated_at");
            return m;
        }

        @Override
        public List<PersonalBudgetMember> findByBudgetIdOrderByIdAsc(String budgetId) {
            return where("budget_id", budgetId);
        }

        @Override
        public List<PersonalBudgetMember> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class PersonalBudgetNotifications extends FirestoreCrud<PersonalBudgetNotification>
            implements FinanceRepositories.PersonalBudgetNotificationRepository {
        PersonalBudgetNotifications(Firestore db) {
            super(db, "budgeting_personal_budget_notifications");
        }

        @Override
        protected Map<String, Object> toDoc(PersonalBudgetNotification n) {
            Map<String, Object> d = new HashMap<>();
            d.put("recipient_id", n.recipientId);
            d.put("budget_id", n.budgetId);
            d.put("shared_by_id", n.sharedById);
            d.put("role", n.role == null || n.role.isEmpty() ? PersonalBudgetMember.VIEWER : n.role);
            d.put("title", n.title);
            d.put("message", n.message == null ? "" : n.message);
            d.put("read_at", ts(n.readAt));
            d.put("created_at", ts(n.createdAt));
            return d;
        }

        @Override
        protected PersonalBudgetNotification fromDoc(String id, Map<String, Object> d) {
            PersonalBudgetNotification n = new PersonalBudgetNotification();
            n.recipientId = str(d, "recipient_id");
            n.budgetId = str(d, "budget_id");
            n.sharedById = str(d, "shared_by_id");
            n.role = strOr(d, "role", PersonalBudgetMember.VIEWER);
            n.title = str(d, "title");
            n.message = str(d, "message");
            n.readAt = instant(d, "read_at");
            n.createdAt = instant(d, "created_at");
            return n;
        }

        @Override
        public List<PersonalBudgetNotification> findByRecipientIdOrderByIdAsc(String recipientId) {
            return where("recipient_id", recipientId);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class PersonalBudgetInvites extends FirestoreCrud<PersonalBudgetInvite>
            implements FinanceRepositories.PersonalBudgetInviteRepository {
        PersonalBudgetInvites(Firestore db) {
            super(db, "budgeting_personal_budget_invites");
        }

        @Override
        protected Map<String, Object> toDoc(PersonalBudgetInvite i) {
            Map<String, Object> d = new HashMap<>();
            d.put("budget_id", i.budgetId);
            d.put("email", i.email == null ? "" : i.email.toLowerCase(Locale.ROOT));
            d.put("role", i.role == null || i.role.isEmpty() ? PersonalBudgetMember.VIEWER : i.role);
            d.put("invited_by_id", i.invitedById);
            d.put("created_at", ts(i.createdAt));
            d.put("updated_at", ts(i.updatedAt));
            return d;
        }

        @Override
        protected PersonalBudgetInvite fromDoc(String id, Map<String, Object> d) {
            PersonalBudgetInvite i = new PersonalBudgetInvite();
            i.budgetId = str(d, "budget_id");
            i.email = str(d, "email").toLowerCase(Locale.ROOT);
            i.role = strOr(d, "role", PersonalBudgetMember.VIEWER);
            i.invitedById = str(d, "invited_by_id");
            i.createdAt = instant(d, "created_at");
            i.updatedAt = instant(d, "updated_at");
            return i;
        }

        @Override
        public List<PersonalBudgetInvite> findByBudgetIdOrderByIdAsc(String budgetId) {
            return where("budget_id", budgetId);
        }

        @Override
        public List<PersonalBudgetInvite> findByEmailOrderByIdAsc(String email) {
            return where("email", email);
        }
    }

    // ---- planning (planning_fs._FsAdapter: user_id, created_at, then the declared fields)

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class IncomeStreams extends FirestoreCrud<IncomeStream> implements FinanceRepositories.IncomeStreamRepository {
        IncomeStreams(Firestore db) {
            super(db, "budgeting_income_streams");
        }

        @Override
        protected Map<String, Object> toDoc(IncomeStream s) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", s.userId);
            d.put("created_at", ts(s.createdAt));
            d.put("name", s.name);
            d.put("amount", decStr(s.amount));
            d.put("currency", s.currency);
            d.put("frequency", s.frequency);
            d.put("account_id", s.accountId);
            d.put("is_active", s.active);
            return d;
        }

        @Override
        protected IncomeStream fromDoc(String id, Map<String, Object> d) {
            IncomeStream s = new IncomeStream();
            s.userId = str(d, "user_id");
            s.createdAt = instant(d, "created_at");
            if (d.containsKey("name")) {
                s.name = str(d, "name");
            }
            if (d.containsKey("amount")) {
                s.amount = decimal(d, "amount");
            }
            if (d.containsKey("currency")) {
                s.currency = str(d, "currency");
            }
            if (d.containsKey("frequency")) {
                s.frequency = str(d, "frequency");
            }
            if (d.containsKey("account_id")) {
                s.accountId = str(d, "account_id");
            }
            if (d.containsKey("is_active")) {
                s.active = bool(d, "is_active", true);
            }
            return s;
        }

        @Override
        public List<IncomeStream> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class GroupBuckets extends FirestoreCrud<GroupBucket> implements FinanceRepositories.GroupBucketRepository {
        GroupBuckets(Firestore db) {
            super(db, "budgeting_group_buckets");
        }

        @Override
        protected Map<String, Object> toDoc(GroupBucket b) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", b.userId);
            d.put("created_at", ts(b.createdAt));
            d.put("group_id", b.groupId);
            d.put("bucket", b.bucket);
            return d;
        }

        @Override
        protected GroupBucket fromDoc(String id, Map<String, Object> d) {
            GroupBucket b = new GroupBucket();
            b.userId = str(d, "user_id");
            b.createdAt = instant(d, "created_at");
            if (d.containsKey("group_id")) {
                b.groupId = str(d, "group_id");
            }
            if (d.containsKey("bucket")) {
                b.bucket = str(d, "bucket");
            }
            return b;
        }

        @Override
        public List<GroupBucket> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class Plans extends FirestoreCrud<BudgetPlan> implements FinanceRepositories.BudgetPlanRepository {
        Plans(Firestore db) {
            super(db, "budgeting_plans");
        }

        @Override
        protected Map<String, Object> toDoc(BudgetPlan p) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", p.userId);
            d.put("created_at", ts(p.createdAt));
            d.put("year", p.year);
            d.put("month", p.month);
            d.put("plan_type", p.planType);
            d.put("status", p.status);
            d.put("reason", p.reason);
            d.put("currency", p.currency);
            d.put("income_total", decStr(p.incomeTotal));
            d.put("commitments_total", decStr(p.commitmentsTotal));
            d.put("available", decStr(p.available));
            d.put("needs_total", decStr(p.needsTotal));
            d.put("wants_total", decStr(p.wantsTotal));
            d.put("savings_amount", decStr(p.savingsAmount));
            d.put("lines", p.lines);
            d.put("warnings", p.warnings);
            d.put("accepted_at", ts(p.acceptedAt));
            return d;
        }

        @Override
        @SuppressWarnings("unchecked")
        protected BudgetPlan fromDoc(String id, Map<String, Object> d) {
            BudgetPlan p = new BudgetPlan();
            p.userId = str(d, "user_id");
            p.createdAt = instant(d, "created_at");
            if (d.containsKey("year")) {
                p.year = integer(d, "year");
            }
            if (d.containsKey("month")) {
                p.month = integer(d, "month");
            }
            if (d.containsKey("plan_type")) {
                p.planType = str(d, "plan_type");
            }
            if (d.containsKey("status")) {
                p.status = str(d, "status");
            }
            if (d.containsKey("reason")) {
                p.reason = str(d, "reason");
            }
            if (d.containsKey("currency")) {
                p.currency = str(d, "currency");
            }
            if (d.containsKey("income_total")) {
                p.incomeTotal = decimal(d, "income_total");
            }
            if (d.containsKey("commitments_total")) {
                p.commitmentsTotal = decimal(d, "commitments_total");
            }
            if (d.containsKey("available")) {
                p.available = decimal(d, "available");
            }
            if (d.containsKey("needs_total")) {
                p.needsTotal = decimal(d, "needs_total");
            }
            if (d.containsKey("wants_total")) {
                p.wantsTotal = decimal(d, "wants_total");
            }
            if (d.containsKey("savings_amount")) {
                p.savingsAmount = decimal(d, "savings_amount");
            }
            if (d.get("lines") instanceof List<?> lines) {
                List<Map<String, Object>> out = new ArrayList<>();
                for (Object line : lines) {
                    if (line instanceof Map<?, ?> m) {
                        out.add(new LinkedHashMap<>((Map<String, Object>) m));
                    }
                }
                p.lines = out;
            }
            if (d.get("warnings") instanceof List<?> warnings) {
                p.warnings = new ArrayList<>(warnings.stream().map(String::valueOf).toList());
            }
            p.acceptedAt = instant(d, "accepted_at");
            return p;
        }

        @Override
        public List<BudgetPlan> findByUserIdOrderByIdAsc(String userId) {
            return where("user_id", userId);
        }
    }
}
