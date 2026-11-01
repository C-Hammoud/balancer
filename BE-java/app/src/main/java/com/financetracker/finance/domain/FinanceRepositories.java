package com.financetracker.finance.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

import org.slf4j.LoggerFactory;

/**
 * Repository ports of the finance module. Abstract methods use Spring Data naming, so the JPA
 * adapters are bare interfaces; the Firestore adapters implement them by hand. Default methods
 * are the list/sort/filter helpers of the Django *FS store classes, shared by both adapters.
 */
public final class FinanceRepositories {

    private static final LocalDate EPOCH = LocalDate.of(1970, 1, 1);

    private FinanceRepositories() {
    }

    private static <T> List<T> limit(List<T> rows, int limit) {
        return rows.size() > limit ? new ArrayList<>(rows.subList(0, limit)) : rows;
    }

    private static Comparator<Instant> instantsNullFirst() {
        return Comparator.nullsFirst(Comparator.naturalOrder());
    }

    private static Optional<String> nonEmpty(String id) {
        return id == null || id.isEmpty() ? Optional.empty() : Optional.of(id);
    }

    // ------------------------------------------------------------------ categories

    public interface GroupRepository {
        Optional<CategoryGroup> findById(String id);

        List<CategoryGroup> findAllByOrderByIdAsc();

        CategoryGroup save(CategoryGroup group);

        void delete(CategoryGroup group);

        default Optional<CategoryGroup> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }
    }

    public interface CategoryRepository {
        Optional<Category> findById(String id);

        List<Category> findAllByOrderByIdAsc();

        Category save(Category category);

        void delete(Category category);

        default Optional<Category> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }
    }

    // ------------------------------------------------------------------ transactions

    public interface TransactionRepository {
        Optional<Transaction> findById(String id);

        List<Transaction> findByUserIdOrderByIdAsc(String userId);

        List<Transaction> findByUserIdAndMonthOrderByIdAsc(String userId, String month);

        List<Transaction> findByBudgetIdOrderByIdAsc(String budgetId);

        boolean existsByUserIdAndExternalId(String userId, String externalId);

        Optional<Transaction> findFirstByUserIdAndExternalIdOrderByIdAsc(String userId, String externalId);

        Transaction save(Transaction transaction);

        void delete(Transaction transaction);

        default Optional<Transaction> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        /** TransactionFS.list_by_user: optional month filter, newest date first. */
        default List<Transaction> listByUser(String userId, String month, int limit) {
            List<Transaction> rows = new ArrayList<>(month == null || month.isEmpty()
                    ? findByUserIdOrderByIdAsc(userId) : findByUserIdAndMonthOrderByIdAsc(userId, month));
            rows.sort(Comparator.comparing((Transaction t) -> t.date == null ? EPOCH : t.date).reversed());
            return limit(rows, limit);
        }

        default List<Transaction> listByBudget(String budgetId, int limit) {
            if (budgetId == null || budgetId.isEmpty()) {
                return List.of();
            }
            List<Transaction> rows = new ArrayList<>(findByBudgetIdOrderByIdAsc(budgetId));
            rows.sort(Comparator.comparing((Transaction t) -> t.date == null ? EPOCH : t.date).reversed());
            return limit(rows, limit);
        }

        default Optional<Transaction> getByExternalId(String userId, String externalId) {
            return findFirstByUserIdAndExternalIdOrderByIdAsc(userId, externalId);
        }
    }

    public interface MerchantLinkRepository {
        Optional<MerchantLink> findById(String id);

        List<MerchantLink> findByUserIdOrderByIdAsc(String userId);

        List<MerchantLink> findAllByOrderByIdAsc();

        MerchantLink save(MerchantLink link);

        void delete(MerchantLink link);

        default Optional<MerchantLink> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }
    }

    // ------------------------------------------------------------------ budgets & savings

    public interface BudgetRepository {
        Optional<Budget> findById(String id);

        List<Budget> findByUserIdOrderByIdAsc(String userId);

        List<Budget> findByUserIdAndYearOrderByIdAsc(String userId, int year);

        List<Budget> findByUserIdAndYearAndMonthOrderByIdAsc(String userId, int year, int month);

        List<Budget> findByUserIdAndGroupIdAndYearAndMonthOrderByIdAsc(String userId, String groupId, int year, int month);

        List<Budget> findByUserIdAndCategoryIdAndYearAndMonthOrderByIdAsc(String userId, String categoryId, int year, int month);

        Budget save(Budget budget);

        /** BudgetFS.list_by_user sorted by (year, month, group_id, category_id). */
        default List<Budget> listByUser(String userId, Integer year, Integer month) {
            List<Budget> rows;
            if (year != null && month != null) {
                rows = new ArrayList<>(findByUserIdAndYearAndMonthOrderByIdAsc(userId, year, month));
            } else if (year != null) {
                rows = new ArrayList<>(findByUserIdAndYearOrderByIdAsc(userId, year));
            } else {
                rows = new ArrayList<>(findByUserIdOrderByIdAsc(userId));
                if (month != null) {
                    rows.removeIf(b -> b.month != month);
                }
            }
            rows.sort(Comparator.comparingInt((Budget b) -> b.year).thenComparingInt(b -> b.month)
                    .thenComparing(b -> b.groupId == null ? "" : b.groupId)
                    .thenComparing(b -> b.categoryId == null ? "" : b.categoryId));
            return rows;
        }

        /** The parent-group budget row (no category) for that month. */
        default Optional<Budget> getByUserGroupMonth(String userId, String groupId, int year, int month) {
            return findByUserIdAndGroupIdAndYearAndMonthOrderByIdAsc(userId, groupId, year, month).stream()
                    .filter(b -> b.categoryId == null || b.categoryId.strip().isEmpty())
                    .findFirst();
        }

        default Optional<Budget> getByUserCategoryMonth(String userId, String categoryId, int year, int month) {
            return findByUserIdAndCategoryIdAndYearAndMonthOrderByIdAsc(userId, categoryId, year, month).stream().findFirst();
        }
    }

    public interface SavingsRepository {
        Optional<Savings> findById(String id);

        List<Savings> findByUserIdOrderByIdAsc(String userId);

        Optional<Savings> findFirstByUserIdAndYearAndMonthOrderByIdAsc(String userId, int year, int month);

        Savings save(Savings savings);

        /** Newest month first. */
        default List<Savings> listByUser(String userId) {
            List<Savings> rows = new ArrayList<>(findByUserIdOrderByIdAsc(userId));
            rows.sort(Comparator.comparingInt((Savings s) -> s.year).thenComparingInt(s -> s.month).reversed());
            return limit(rows, 100);
        }

        default Optional<Savings> getByUserMonth(String userId, int year, int month) {
            return findFirstByUserIdAndYearAndMonthOrderByIdAsc(userId, year, month);
        }
    }

    // ------------------------------------------------------------------ commitments

    public interface CommitmentRepository {
        Optional<Commitment> findById(String id);

        List<Commitment> findByUserIdOrderByIdAsc(String userId);

        Commitment save(Commitment commitment);

        void delete(Commitment commitment);

        default Optional<Commitment> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        default List<Commitment> listByUser(String userId) {
            return findByUserIdOrderByIdAsc(userId);
        }
    }

    public interface ScheduleLineRepository {
        Optional<ScheduleLine> findById(String id);

        List<ScheduleLine> findByCommitmentIdOrderByIdAsc(String commitmentId);

        ScheduleLine save(ScheduleLine line);

        void delete(ScheduleLine line);

        default Optional<ScheduleLine> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        /**
         * CommitmentScheduleLineFS.list_by_commitment: sorted by (due date, sequence); duplicate
         * installments left by older schedule generation are removed (the best copy is kept).
         */
        default List<ScheduleLine> listByCommitment(String commitmentId) {
            List<ScheduleLine> rows = new ArrayList<>(findByCommitmentIdOrderByIdAsc(commitmentId));
            rows.sort(lineOrder());
            if (rows.size() > 1) {
                rows = dedupeAndCleanup(rows);
            }
            return rows;
        }

        private static Comparator<ScheduleLine> lineOrder() {
            return Comparator.comparing((ScheduleLine l) -> l.dueDate == null ? EPOCH : l.dueDate)
                    .thenComparingInt(l -> l.sequence);
        }

        private List<ScheduleLine> dedupeAndCleanup(List<ScheduleLine> lines) {
            Map<Integer, ScheduleLine> bySeq = new LinkedHashMap<>();
            for (ScheduleLine line : lines) {
                if (line.sequence <= 0) {
                    continue;
                }
                ScheduleLine prev = bySeq.get(line.sequence);
                if (prev == null) {
                    bySeq.put(line.sequence, line);
                    continue;
                }
                ScheduleLine[] keepDrop = pickPreferred(prev, line);
                bySeq.put(line.sequence, keepDrop[0]);
                deleteDuplicate(keepDrop[0], keepDrop[1]);
            }
            Map<String, ScheduleLine> byDue = new LinkedHashMap<>();
            for (ScheduleLine line : lines) {
                if (line.sequence > 0) {
                    continue;
                }
                String key = line.dueDate + "|" + line.amount + "|" + line.status;
                ScheduleLine prev = byDue.get(key);
                if (prev == null) {
                    byDue.put(key, line);
                    continue;
                }
                ScheduleLine[] keepDrop = pickPreferred(prev, line);
                byDue.put(key, keepDrop[0]);
                deleteDuplicate(keepDrop[0], keepDrop[1]);
            }
            List<ScheduleLine> merged = new ArrayList<>(bySeq.values());
            merged.addAll(byDue.values());
            merged.sort(lineOrder());
            return merged;
        }

        private void deleteDuplicate(ScheduleLine keep, ScheduleLine drop) {
            if (drop.id != null && !drop.id.equals(keep.id)) {
                try {
                    delete(drop);
                } catch (RuntimeException e) {
                    LoggerFactory.getLogger(ScheduleLineRepository.class)
                            .warn("Failed to delete duplicate schedule line {}: {}", drop.id, e.getMessage());
                }
            }
        }

        /** Returns {keep, drop}: paid beats outstanding, then a paid date, then the older id. */
        private static ScheduleLine[] pickPreferred(ScheduleLine a, ScheduleLine b) {
            boolean aPaid = ScheduleLine.PAID.equals(a.status);
            boolean bPaid = ScheduleLine.PAID.equals(b.status);
            if (aPaid && !bPaid) {
                return new ScheduleLine[] {a, b};
            }
            if (bPaid && !aPaid) {
                return new ScheduleLine[] {b, a};
            }
            if (a.paidDate != null && b.paidDate == null) {
                return new ScheduleLine[] {a, b};
            }
            if (b.paidDate != null && a.paidDate == null) {
                return new ScheduleLine[] {b, a};
            }
            String ap = a.id == null ? "" : a.id;
            String bp = b.id == null ? "" : b.id;
            return ap.compareTo(bp) <= 0 ? new ScheduleLine[] {a, b} : new ScheduleLine[] {b, a};
        }

        default int deleteByCommitment(String commitmentId) {
            List<ScheduleLine> lines = listByCommitment(commitmentId);
            lines.forEach(this::delete);
            return lines.size();
        }

        default BigDecimal sumOutstandingByCommitment(String commitmentId) {
            BigDecimal total = BigDecimal.ZERO;
            for (ScheduleLine l : listByCommitment(commitmentId)) {
                if (ScheduleLine.OUTSTANDING.equals(l.status)) {
                    total = total.add(l.amount);
                }
            }
            return total;
        }
    }

    public interface FinancialStandingRepository {
        List<FinancialStanding> findByUserIdOrderByIdAsc(String userId);

        FinancialStanding save(FinancialStanding standing);

        /** Newest snapshot first. */
        default List<FinancialStanding> listByUser(String userId) {
            List<FinancialStanding> rows = new ArrayList<>(findByUserIdOrderByIdAsc(userId));
            rows.sort(Comparator.comparing((FinancialStanding s) -> s.snapshotDate == null ? EPOCH : s.snapshotDate).reversed());
            return limit(rows, 100);
        }
    }

    // ------------------------------------------------------------------ configuration

    public interface TypeCategoryMapRepository {
        List<TypeCategoryMap> findByUserIdOrderByIdAsc(String userId);

        List<TypeCategoryMap> findAllByOrderByIdAsc();

        TypeCategoryMap save(TypeCategoryMap map);

        void delete(TypeCategoryMap map);

        /** Global defaults (no user). */
        default List<TypeCategoryMap> listGlobal() {
            return findAllByOrderByIdAsc().stream().filter(m -> m.userId == null || m.userId.isEmpty()).toList();
        }

        /** consumption_type -> category_id; the user's maps override the global ones. */
        default Map<String, String> mapForUser(String userId) {
            Map<String, String> result = new HashMap<>();
            for (TypeCategoryMap m : listGlobal()) {
                if (m.consumptionType != null && !m.consumptionType.isEmpty()) {
                    result.put(m.consumptionType.toLowerCase(Locale.ROOT), m.categoryId);
                }
            }
            for (TypeCategoryMap m : findByUserIdOrderByIdAsc(userId)) {
                if (m.consumptionType != null && !m.consumptionType.isEmpty()) {
                    result.put(m.consumptionType.toLowerCase(Locale.ROOT), m.categoryId);
                }
            }
            return result;
        }
    }

    public interface BudgetThresholdRepository {
        Optional<BudgetThreshold> findById(String id);

        List<BudgetThreshold> findByUserIdOrderByIdAsc(String userId);

        BudgetThreshold save(BudgetThreshold threshold);

        void delete(BudgetThreshold threshold);

        default Optional<BudgetThreshold> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        /** Category-specific threshold if set, else the user's global one. */
        default Optional<BudgetThreshold> getForCategory(String userId, String categoryId) {
            List<BudgetThreshold> all = findByUserIdOrderByIdAsc(userId);
            if (categoryId != null && !categoryId.isEmpty()) {
                for (BudgetThreshold t : all) {
                    if (categoryId.equals(t.categoryId)) {
                        return Optional.of(t);
                    }
                }
            }
            return all.stream().filter(t -> t.categoryId == null || t.categoryId.isEmpty()).findFirst();
        }

        /** The threshold stored for exactly this category (null/blank = the global row); no fallback. */
        default Optional<BudgetThreshold> getExact(String userId, String categoryId) {
            String wanted = categoryId == null || categoryId.isEmpty() ? null : categoryId;
            return findByUserIdOrderByIdAsc(userId).stream()
                    .filter(t -> java.util.Objects.equals(
                            t.categoryId == null || t.categoryId.isEmpty() ? null : t.categoryId, wanted))
                    .findFirst();
        }
    }

    public interface AccountRepository {
        Optional<Account> findById(String id);

        List<Account> findByUserIdOrderByIdAsc(String userId);

        Account save(Account account);

        void delete(Account account);

        default Optional<Account> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        /** Sorted by (order, lower(name)). */
        default List<Account> listByUser(String userId, boolean activeOnly) {
            List<Account> rows = new ArrayList<>(findByUserIdOrderByIdAsc(userId));
            if (activeOnly) {
                rows.removeIf(a -> !a.active);
            }
            rows.sort(Comparator.comparingInt((Account a) -> a.order).thenComparing(a -> a.name.toLowerCase(Locale.ROOT)));
            return rows;
        }
    }

    // ------------------------------------------------------------------ alerts

    public interface BudgetAlertRepository {
        Optional<BudgetAlert> findById(String id);

        List<BudgetAlert> findByUserIdOrderByIdAsc(String userId);

        BudgetAlert save(BudgetAlert alert);

        default Optional<BudgetAlert> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        /** Newest first. */
        default List<BudgetAlert> listByUser(String userId, boolean openOnly, int limit) {
            List<BudgetAlert> rows = new ArrayList<>(findByUserIdOrderByIdAsc(userId));
            if (openOnly) {
                rows.removeIf(a -> a.isResolved);
            }
            rows.sort(Comparator.comparing((BudgetAlert a) -> a.createdAt, instantsNullFirst()).reversed());
            return limit(rows, limit);
        }

        /** Open alerts that are not snoozed (badge count). */
        default int countOpen(String userId, Instant now) {
            return (int) listByUser(userId, true, 500).stream().filter(a -> !a.isSnoozed(now)).count();
        }
    }

    // ------------------------------------------------------------------ personal budgets

    public interface PersonalBudgetRepository {
        Optional<PersonalBudget> findById(String id);

        List<PersonalBudget> findByUserIdOrderByIdAsc(String userId);

        PersonalBudget save(PersonalBudget budget);

        void delete(PersonalBudget budget);

        default Optional<PersonalBudget> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        /** Default budget first, then by name. */
        default List<PersonalBudget> listByUser(String userId) {
            List<PersonalBudget> rows = new ArrayList<>(findByUserIdOrderByIdAsc(userId));
            rows.sort(Comparator.comparing((PersonalBudget b) -> !b.isDefault)
                    .thenComparing(b -> b.name.toLowerCase(Locale.ROOT)));
            return rows;
        }

        default Optional<PersonalBudget> getDefaultForUser(String userId) {
            return listByUser(userId).stream().filter(b -> b.isDefault).findFirst();
        }
    }

    public interface PersonalBudgetCategoryRepository {
        Optional<PersonalBudgetCategory> findById(String id);

        List<PersonalBudgetCategory> findByBudgetIdOrderByIdAsc(String budgetId);

        PersonalBudgetCategory save(PersonalBudgetCategory category);

        void delete(PersonalBudgetCategory category);

        default Optional<PersonalBudgetCategory> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        /** Sorted by (order, lower(name)). */
        default List<PersonalBudgetCategory> listByBudget(String budgetId) {
            List<PersonalBudgetCategory> rows = new ArrayList<>(findByBudgetIdOrderByIdAsc(budgetId));
            rows.sort(Comparator.comparingInt((PersonalBudgetCategory c) -> c.order)
                    .thenComparing(c -> c.name.toLowerCase(Locale.ROOT)));
            return rows;
        }
    }

    public interface PersonalBudgetMemberRepository {
        Optional<PersonalBudgetMember> findById(String id);

        List<PersonalBudgetMember> findByBudgetIdOrderByIdAsc(String budgetId);

        List<PersonalBudgetMember> findByUserIdOrderByIdAsc(String userId);

        PersonalBudgetMember save(PersonalBudgetMember member);

        void delete(PersonalBudgetMember member);

        default Optional<PersonalBudgetMember> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        /** Oldest first. */
        default List<PersonalBudgetMember> listByBudget(String budgetId) {
            List<PersonalBudgetMember> rows = new ArrayList<>(findByBudgetIdOrderByIdAsc(budgetId));
            rows.sort(Comparator.comparing((PersonalBudgetMember m) -> m.createdAt, instantsNullFirst()));
            return rows;
        }

        /** Newest first. */
        default List<PersonalBudgetMember> listByUser(String userId) {
            List<PersonalBudgetMember> rows = new ArrayList<>(findByUserIdOrderByIdAsc(userId));
            rows.sort(Comparator.comparing((PersonalBudgetMember m) -> m.createdAt, instantsNullFirst()).reversed());
            return rows;
        }

        default Optional<PersonalBudgetMember> getForBudgetUser(String budgetId, String userId) {
            return listByBudget(budgetId).stream().filter(m -> String.valueOf(userId).equals(m.userId)).findFirst();
        }
    }

    public interface PersonalBudgetNotificationRepository {
        Optional<PersonalBudgetNotification> findById(String id);

        List<PersonalBudgetNotification> findByRecipientIdOrderByIdAsc(String recipientId);

        PersonalBudgetNotification save(PersonalBudgetNotification notification);

        default Optional<PersonalBudgetNotification> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        /** Newest first. */
        default List<PersonalBudgetNotification> listForRecipient(String userId, int limit) {
            List<PersonalBudgetNotification> rows = new ArrayList<>(findByRecipientIdOrderByIdAsc(userId));
            rows.sort(Comparator.comparing((PersonalBudgetNotification n) -> n.createdAt, instantsNullFirst()).reversed());
            return limit(rows, limit);
        }
    }

    public interface PersonalBudgetInviteRepository {
        Optional<PersonalBudgetInvite> findById(String id);

        List<PersonalBudgetInvite> findByBudgetIdOrderByIdAsc(String budgetId);

        List<PersonalBudgetInvite> findByEmailOrderByIdAsc(String email);

        PersonalBudgetInvite save(PersonalBudgetInvite invite);

        void delete(PersonalBudgetInvite invite);

        default Optional<PersonalBudgetInvite> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        /** Oldest first. */
        default List<PersonalBudgetInvite> listByBudget(String budgetId) {
            List<PersonalBudgetInvite> rows = new ArrayList<>(findByBudgetIdOrderByIdAsc(budgetId));
            rows.sort(Comparator.comparing((PersonalBudgetInvite i) -> i.createdAt, instantsNullFirst()));
            return rows;
        }

        default List<PersonalBudgetInvite> listByEmail(String email) {
            return findByEmailOrderByIdAsc(email == null ? "" : email.strip().toLowerCase(Locale.ROOT));
        }

        default Optional<PersonalBudgetInvite> getForBudgetEmail(String budgetId, String email) {
            String e = email == null ? "" : email.strip().toLowerCase(Locale.ROOT);
            return listByBudget(budgetId).stream().filter(i -> e.equals(i.email)).findFirst();
        }
    }

    // ------------------------------------------------------------------ planning

    public interface IncomeStreamRepository {
        Optional<IncomeStream> findById(String id);

        List<IncomeStream> findByUserIdOrderByIdAsc(String userId);

        IncomeStream save(IncomeStream stream);

        void delete(IncomeStream stream);

        default Optional<IncomeStream> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        /** Newest first. */
        default List<IncomeStream> listByUser(String userId) {
            List<IncomeStream> rows = new ArrayList<>(findByUserIdOrderByIdAsc(userId));
            rows.sort(Comparator.comparing((IncomeStream s) -> s.createdAt, instantsNullFirst()).reversed());
            return limit(rows, 500);
        }
    }

    public interface GroupBucketRepository {
        List<GroupBucket> findByUserIdOrderByIdAsc(String userId);

        GroupBucket save(GroupBucket bucket);

        default List<GroupBucket> listByUser(String userId) {
            List<GroupBucket> rows = new ArrayList<>(findByUserIdOrderByIdAsc(userId));
            rows.sort(Comparator.comparing((GroupBucket b) -> b.createdAt, instantsNullFirst()).reversed());
            return rows;
        }
    }

    public interface BudgetPlanRepository {
        Optional<BudgetPlan> findById(String id);

        List<BudgetPlan> findByUserIdOrderByIdAsc(String userId);

        BudgetPlan save(BudgetPlan plan);

        default Optional<BudgetPlan> get(String id) {
            return nonEmpty(id).flatMap(this::findById);
        }

        /** Newest first. */
        default List<BudgetPlan> listByUser(String userId, int limit) {
            List<BudgetPlan> rows = new ArrayList<>(findByUserIdOrderByIdAsc(userId));
            rows.sort(Comparator.comparing((BudgetPlan p) -> p.createdAt, instantsNullFirst()).reversed());
            return limit(rows, limit);
        }

        default List<BudgetPlan> listForMonth(String userId, int year, int month) {
            List<BudgetPlan> rows = new ArrayList<>(listByUser(userId, Integer.MAX_VALUE));
            rows.removeIf(p -> p.year != year || p.month != month);
            return limit(rows, 500);
        }
    }
}
