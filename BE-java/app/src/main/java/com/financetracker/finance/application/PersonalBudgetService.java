package com.financetracker.finance.application;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import org.springframework.stereotype.Service;

import com.financetracker.finance.domain.FinanceRepositories.CategoryRepository;
import com.financetracker.finance.domain.FinanceRepositories.GroupRepository;
import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetCategoryRepository;
import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetRepository;
import com.financetracker.finance.domain.FinanceRepositories.TransactionRepository;
import com.financetracker.finance.domain.PersonalBudget;
import com.financetracker.finance.domain.PersonalBudgetCategory;
import com.financetracker.finance.domain.PersonalBudgetMember;
import com.financetracker.finance.domain.Transaction;
import com.financetracker.shared.locale.ExchangeRates;
import com.financetracker.shared.web.Py;

/** Port of budgeting/personal_budget_service.py. */
@Service
public class PersonalBudgetService {

    private static final String UNCATEGORIZED = "_uncategorized_";

    private final PersonalBudgetRepository budgets;
    private final PersonalBudgetCategoryRepository categories;
    private final TransactionRepository transactions;
    private final GroupRepository groups;
    private final CategoryRepository financeCategories;
    private final PersonalBudgetAccess access;
    private final ExchangeRates rates;
    private final Clock clock;

    public PersonalBudgetService(PersonalBudgetRepository budgets, PersonalBudgetCategoryRepository categories,
            TransactionRepository transactions, GroupRepository groups, CategoryRepository financeCategories,
            PersonalBudgetAccess access, ExchangeRates rates, Clock clock) {
        this.budgets = budgets;
        this.categories = categories;
        this.transactions = transactions;
        this.groups = groups;
        this.financeCategories = financeCategories;
        this.access = access;
        this.rates = rates;
        this.clock = clock;
    }

    /** The default budget, creating "Monthly Expenses" for the current year if there is none. */
    public PersonalBudget ensureDefault(String userId) {
        var existing = budgets.getDefaultForUser(userId);
        if (existing.isPresent()) {
            return existing.get();
        }
        List<PersonalBudget> rows = budgets.listByUser(userId);
        if (!rows.isEmpty()) {
            PersonalBudget first = rows.get(0);
            first.isDefault = true;
            first.status = PersonalBudget.ACTIVE;
            budgets.save(first);
            return first;
        }
        LocalDate today = clock.instant().atOffset(ZoneOffset.UTC).toLocalDate();
        PersonalBudget b = new PersonalBudget();
        b.userId = userId;
        b.name = "Monthly Expenses";
        b.description = "Default monthly personal budget";
        b.currency = "USD";
        b.startDate = LocalDate.of(today.getYear(), 1, 1);
        b.endDate = LocalDate.of(today.getYear(), 12, 31);
        b.totalAmount = Dec.ZERO;
        b.status = PersonalBudget.ACTIVE;
        b.isDefault = true;
        budgets.save(b);
        return b;
    }

    private BigDecimal expenseTotal(String budgetId, String currency) {
        BigDecimal total = Dec.ZERO;
        for (Transaction t : transactions.listByBudget(budgetId, 2000)) {
            if ("expense".equals(t.direction)) {
                total = total.add(rates.convert(t.amount, t.currency == null || t.currency.isEmpty() ? "USD" : t.currency, currency));
            }
        }
        return total;
    }

    private Map<String, BigDecimal> spentByCategory(String budgetId, String currency) {
        Map<String, BigDecimal> out = new LinkedHashMap<>();
        for (Transaction t : transactions.listByBudget(budgetId, 2000)) {
            if (!"expense".equals(t.direction)) {
                continue;
            }
            String catId = t.budgetCategoryId == null || t.budgetCategoryId.isEmpty() ? UNCATEGORIZED : t.budgetCategoryId;
            out.merge(catId, rates.convert(t.amount, t.currency == null || t.currency.isEmpty() ? "USD" : t.currency, currency),
                    BigDecimal::add);
        }
        return out;
    }

    /** serialize_budget_summary. accessRole null = owner when the user owns it. */
    public Map<String, Object> summary(PersonalBudget b, String userId, boolean includeCategories, String accessRole) {
        String currency = b.currency == null || b.currency.isEmpty() ? "USD" : b.currency;
        BigDecimal spent = expenseTotal(b.id, currency);
        BigDecimal total = Dec.orZero(b.totalAmount);
        BigDecimal remaining = total.subtract(spent);
        double pct = total.signum() > 0 ? Dec.q(Dec.mul(Dec.div(spent, total), Dec.HUNDRED), 1).doubleValue() : 0.0;
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("id", b.id);
        data.put("user_id", b.userId);
        data.put("name", b.name);
        data.put("description", b.description == null ? "" : b.description);
        data.put("currency", currency);
        data.put("start_date", Py.isoformat(b.startDate));
        data.put("end_date", Py.isoformat(b.endDate));
        data.put("total_amount", Py.dec(total));
        data.put("status", b.status);
        data.put("project_tag", b.projectTag == null ? "" : b.projectTag);
        data.put("notes", b.notes == null ? "" : b.notes);
        data.put("is_default", b.isDefault);
        data.put("spent", Py.dec(Dec.q(spent, 2)));
        data.put("remaining", Py.dec(Dec.q(remaining, 2)));
        data.put("percent_used", pct);
        data.put("created_at", Py.isoformat(b.createdAt));
        data.put("updated_at", Py.isoformat(b.updatedAt));
        String role = accessRole;
        if (role == null) {
            role = String.valueOf(b.userId).equals(userId) ? PersonalBudgetMember.OWNER : null;
        }
        if (role != null) {
            data.put("access_role", role);
            data.put("is_owner", PersonalBudgetMember.OWNER.equals(role));
        }
        if (includeCategories) {
            List<Map<String, Object>> cats = categoryTree(b.id, currency);
            data.put("categories", cats);
            BigDecimal allocated = Dec.ZERO;
            for (Map<String, Object> c : cats) {
                Object parent = c.get("parent_id");
                if (!UNCATEGORIZED.equals(c.get("id")) && (parent == null || "".equals(parent))) {
                    allocated = allocated.add(Dec.parseOrZero(c.get("allocated_amount")));
                }
            }
            data.put("categories_allocated_total", Py.dec(allocated));
        }
        return data;
    }

    private static Map<String, Object> categoryRow(PersonalBudgetCategory c, Map<String, BigDecimal> spentMap) {
        BigDecimal alloc = Dec.orZero(c.allocatedAmount);
        BigDecimal spent = spentMap.getOrDefault(c.id, Dec.ZERO);
        Map<String, Object> row = new LinkedHashMap<>();
        row.put("id", c.id);
        row.put("budget_id", c.budgetId);
        row.put("name", c.name);
        row.put("allocated_amount", Py.dec(alloc));
        row.put("spent", Py.dec(Dec.q(spent, 2)));
        row.put("remaining", Py.dec(Dec.q(alloc.subtract(spent), 2)));
        row.put("order", c.order);
        row.put("notes", c.notes == null ? "" : c.notes);
        row.put("group_id", c.groupId == null ? "" : c.groupId);
        row.put("category_id", c.categoryId == null ? "" : c.categoryId);
        row.put("parent_id", c.parentId == null ? "" : c.parentId);
        return row;
    }

    private static Comparator<Map<String, Object>> rowOrder() {
        return Comparator.comparingInt((Map<String, Object> r) -> (Integer) r.getOrDefault("order", 0))
                .thenComparing(r -> String.valueOf(r.getOrDefault("name", "")).toLowerCase(Locale.ROOT));
    }

    private List<Map<String, Object>> categoryTree(String budgetId, String currency) {
        Map<String, BigDecimal> spentMap = spentByCategory(budgetId, currency);
        Map<String, List<Map<String, Object>>> byParent = new LinkedHashMap<>();
        List<Map<String, Object>> roots = new ArrayList<>();
        for (PersonalBudgetCategory c : categories.listByBudget(budgetId)) {
            Map<String, Object> row = categoryRow(c, spentMap);
            String parentId = c.parentId == null ? "" : c.parentId;
            if (!parentId.isEmpty()) {
                byParent.computeIfAbsent(parentId, k -> new ArrayList<>()).add(row);
            } else {
                roots.add(row);
            }
        }
        for (Map<String, Object> root : roots) {
            List<Map<String, Object>> subs = byParent.getOrDefault(String.valueOf(root.get("id")), new ArrayList<>());
            subs.sort(rowOrder());
            root.put("sub_categories", subs);
        }
        BigDecimal uncSpent = spentMap.getOrDefault(UNCATEGORIZED, Dec.ZERO);
        if (uncSpent.signum() > 0) {
            Map<String, Object> unc = new LinkedHashMap<>();
            unc.put("id", UNCATEGORIZED);
            unc.put("budget_id", budgetId);
            unc.put("name", "Uncategorized");
            unc.put("allocated_amount", "0");
            unc.put("spent", Py.dec(Dec.q(uncSpent, 2)));
            unc.put("remaining", Py.dec(Dec.q(uncSpent.negate(), 2)));
            unc.put("order", 9999);
            unc.put("notes", "");
            unc.put("group_id", "");
            unc.put("category_id", "");
            unc.put("parent_id", "");
            unc.put("sub_categories", new ArrayList<>());
            roots.add(unc);
        }
        roots.sort(rowOrder());
        return roots;
    }

    /** list_personal_budgets: the user's own budgets with filters and sorting. */
    public List<Map<String, Object>> list(String userId, String search, String status, String sort, LocalDate periodStart,
            LocalDate periodEnd) {
        ensureDefault(userId);
        List<PersonalBudget> rows = new ArrayList<>(budgets.listByUser(userId));
        if (search != null && !search.isEmpty()) {
            String q = search.strip().toLowerCase(Locale.ROOT);
            rows.removeIf(b -> !(nz(b.name).toLowerCase(Locale.ROOT).contains(q) || nz(b.description).toLowerCase(Locale.ROOT).contains(q)));
        }
        if (status != null && !status.isEmpty()) {
            rows.removeIf(b -> !status.equals(b.status));
        }
        if (periodStart != null || periodEnd != null) {
            rows.removeIf(b -> (periodStart != null && b.endDate != null && b.endDate.isBefore(periodStart))
                    || (periodEnd != null && b.startDate != null && b.startDate.isAfter(periodEnd)));
        }
        List<Map<String, Object>> summaries = new ArrayList<>();
        for (PersonalBudget b : rows) {
            summaries.add(summary(b, userId, false, PersonalBudgetMember.OWNER));
        }
        switch (sort == null ? "created_desc" : sort) {
            case "name" -> summaries.sort(Comparator.comparing(x -> nz((String) x.get("name")).toLowerCase(Locale.ROOT)));
            case "amount" -> summaries.sort(Comparator.comparing((Map<String, Object> x) -> Dec.parseOrZero(x.get("total_amount"))).reversed());
            case "spent" -> summaries.sort(Comparator.comparing((Map<String, Object> x) -> Dec.parseOrZero(x.get("spent"))).reversed());
            case "created_asc" -> summaries.sort(Comparator.comparing(x -> nz((String) x.get("created_at"))));
            default -> summaries.sort(Comparator.comparing((Map<String, Object> x) -> nz((String) x.get("created_at"))).reversed());
        }
        return summaries;
    }

    private static String nz(String s) {
        return s == null ? "" : s;
    }

    public Map<String, Object> dashboard(String userId, List<Map<String, Object>> sharedWithMe) {
        List<Map<String, Object>> all = list(userId, "", "", "created_desc", null, null);
        List<Map<String, Object>> active = all.stream()
                .filter(b -> !PersonalBudget.ARCHIVED.equals(b.get("status")) && !PersonalBudget.DRAFT.equals(b.get("status")))
                .toList();
        BigDecimal allocated = Dec.ZERO;
        BigDecimal spent = Dec.ZERO;
        for (Map<String, Object> b : active) {
            allocated = allocated.add(Dec.parseOrZero(b.get("total_amount")));
            spent = spent.add(Dec.parseOrZero(b.get("spent")));
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("total_budgets", all.size());
        out.put("active_budgets", active.size());
        out.put("total_allocated", Py.dec(Dec.q(allocated, 2)));
        out.put("total_spent", Py.dec(Dec.q(spent, 2)));
        out.put("total_remaining", Py.dec(Dec.q(allocated.subtract(spent), 2)));
        out.put("budgets", all);
        out.put("shared_with_me", sharedWithMe);
        return out;
    }

    private static String strip(Object v) {
        return v == null ? "" : Py.str(v).strip();
    }

    private static int intOr(Object v, int dflt) {
        if (!Py.truthy(v)) {
            return dflt;
        }
        Integer i = com.financetracker.shared.web.RequestData.parseInt(v);
        if (i == null) {
            throw new PersonalBudgetAccess.Invalid("A valid integer is required.");
        }
        return i;
    }

    /** create_personal_budget_category (group line with optional sub-lines, or a free-text line). */
    @SuppressWarnings("unchecked")
    public Map<String, Object> createCategory(String budgetId, String userId, Map<String, Object> data) {
        PersonalBudget budget = access.requireEdit(userId, budgetId).budget();
        String groupId = strip(data.get("group_id"));
        String name = strip(data.get("name"));
        if (!groupId.isEmpty() && name.isEmpty()) {
            name = groups.get(groupId).map(g -> g.name).orElse("");
        }
        if (name.isEmpty() && groupId.isEmpty()) {
            throw new PersonalBudgetAccess.Invalid("Category name or group_id is required.");
        }
        BigDecimal allocated = Dec.parseOrZero(data.getOrDefault("allocated_amount", "0"));
        if (!groupId.isEmpty() && allocated.signum() <= 0) {
            throw new PersonalBudgetAccess.Invalid("Maximum utilization must be greater than zero.");
        }
        if (groupId.isEmpty()) {
            PersonalBudgetCategory c = new PersonalBudgetCategory();
            c.budgetId = budgetId;
            c.name = name;
            c.allocatedAmount = allocated;
            c.order = intOr(data.get("order"), 0);
            c.notes = Py.truthy(data.get("notes")) ? Py.str(data.get("notes")) : "";
            categories.save(c);
            return summary(budget, userId, true, null);
        }
        PersonalBudgetCategory parent = new PersonalBudgetCategory();
        parent.budgetId = budgetId;
        parent.name = name.isEmpty() ? "Category" : name;
        parent.allocatedAmount = allocated;
        parent.order = intOr(data.get("order"), 0);
        parent.notes = Py.truthy(data.get("notes")) ? Py.str(data.get("notes")) : "";
        parent.groupId = groupId;
        categories.save(parent);

        Object rawSubs = Py.truthy(data.get("subcategories")) ? data.get("subcategories") : data.get("sub_categories");
        List<Object> subs = rawSubs instanceof List<?> l ? (List<Object>) l : List.of();
        for (int idx = 0; idx < subs.size(); idx++) {
            if (!(subs.get(idx) instanceof Map<?, ?> m)) {
                continue;
            }
            Map<String, Object> sub = (Map<String, Object>) m;
            String amountRaw = strip(sub.get("allocated_amount"));
            if (amountRaw.isEmpty() || Dec.parseOrZero(amountRaw).signum() <= 0) {
                continue;
            }
            String subCatId = strip(sub.get("category_id"));
            String subName = strip(sub.get("name"));
            if (!subCatId.isEmpty() && subName.isEmpty()) {
                subName = financeCategories.get(subCatId).map(c -> c.name).orElse("");
            }
            if (subName.isEmpty()) {
                continue;
            }
            PersonalBudgetCategory c = new PersonalBudgetCategory();
            c.budgetId = budgetId;
            c.name = subName;
            c.allocatedAmount = Dec.parseOrZero(amountRaw);
            c.order = intOr(sub.getOrDefault("order", idx), idx);
            c.notes = Py.truthy(sub.get("notes")) ? Py.str(sub.get("notes")) : "";
            c.groupId = groupId;
            c.categoryId = subCatId;
            c.parentId = parent.id;
            categories.save(c);
        }
        return summary(budget, userId, true, null);
    }

    /** create_personal_budget(user, data); dates already parsed by the controller. */
    @SuppressWarnings("unchecked")
    public Map<String, Object> create(String userId, Map<String, Object> data, LocalDate start, LocalDate end) {
        PersonalBudget b = new PersonalBudget();
        b.userId = userId;
        b.name = Py.str(data.get("name"));
        b.description = data.containsKey("description") ? str(data.get("description")) : "";
        b.currency = Py.truthy(data.get("currency")) ? Py.str(data.get("currency")) : "USD";
        b.startDate = start;
        b.endDate = end;
        b.totalAmount = Dec.parseOrZero(data.getOrDefault("total_amount", "0"));
        b.status = Py.truthy(data.get("status")) ? Py.str(data.get("status")) : PersonalBudget.DRAFT;
        b.projectTag = data.containsKey("project_tag") ? str(data.get("project_tag")) : "";
        b.notes = data.containsKey("notes") ? str(data.get("notes")) : "";
        b.isDefault = Py.truthy(data.get("is_default"));
        if (b.isDefault) {
            for (PersonalBudget row : budgets.listByUser(userId)) {
                if (row.isDefault) {
                    row.isDefault = false;
                    budgets.save(row);
                }
            }
        }
        budgets.save(b);
        Object cats = data.get("categories");
        if (cats instanceof List<?> list) {
            for (int idx = 0; idx < list.size(); idx++) {
                if (!(list.get(idx) instanceof Map<?, ?> m)) {
                    continue;
                }
                Map<String, Object> cat = (Map<String, Object>) m;
                PersonalBudgetCategory c = new PersonalBudgetCategory();
                c.budgetId = b.id;
                c.name = Py.str(cat.get("name"));
                c.allocatedAmount = Dec.parseOrZero(cat.getOrDefault("allocated_amount", "0"));
                Integer order = com.financetracker.shared.web.RequestData.parseInt(cat.getOrDefault("order", idx));
                c.order = order == null ? idx : order;
                c.notes = cat.containsKey("notes") ? str(cat.get("notes")) : "";
                c.groupId = Py.truthy(cat.get("group_id")) ? Py.str(cat.get("group_id")) : "";
                c.categoryId = Py.truthy(cat.get("category_id")) ? Py.str(cat.get("category_id")) : "";
                c.parentId = Py.truthy(cat.get("parent_id")) ? Py.str(cat.get("parent_id")) : "";
                categories.save(c);
            }
        }
        return summary(b, userId, true, null);
    }

    private static String str(Object v) {
        return v == null ? "" : Py.str(v);
    }

    /** update_personal_budget; startDate/endDate are applied only when the keys are present. */
    public Map<String, Object> update(String userId, String budgetId, Map<String, Object> data, LocalDate start, LocalDate end) {
        PersonalBudget b = access.requireEdit(userId, budgetId).budget();
        if (data.containsKey("name")) {
            b.name = Py.truthy(data.get("name")) ? Py.str(data.get("name")) : "";
        }
        if (data.containsKey("description")) {
            b.description = Py.truthy(data.get("description")) ? Py.str(data.get("description")) : "";
        }
        if (data.containsKey("currency")) {
            b.currency = Py.truthy(data.get("currency")) ? Py.str(data.get("currency")) : "";
        }
        if (data.containsKey("status")) {
            b.status = Py.truthy(data.get("status")) ? Py.str(data.get("status")) : "";
        }
        if (data.containsKey("project_tag")) {
            b.projectTag = Py.truthy(data.get("project_tag")) ? Py.str(data.get("project_tag")) : "";
        }
        if (data.containsKey("notes")) {
            b.notes = Py.truthy(data.get("notes")) ? Py.str(data.get("notes")) : "";
        }
        if (data.containsKey("start_date")) {
            b.startDate = start;
        }
        if (data.containsKey("end_date")) {
            b.endDate = end;
        }
        if (data.containsKey("total_amount")) {
            b.totalAmount = Dec.parseOrZero(data.get("total_amount"));
        }
        if (Py.truthy(data.get("is_default"))) {
            for (PersonalBudget row : budgets.listByUser(userId)) {
                if (!row.id.equals(b.id) && row.isDefault) {
                    row.isDefault = false;
                    budgets.save(row);
                }
            }
            b.isDefault = true;
        }
        budgets.save(b);
        return summary(b, userId, true, null);
    }

    /** clone_personal_budget: owner only; copies categories. */
    public Map<String, Object> cloneBudget(String userId, String budgetId, Map<String, Object> data, LocalDate start,
            LocalDate end) {
        PersonalBudget source = access.requireOwner(userId, budgetId);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("name", Py.truthy(data.get("name")) ? data.get("name") : source.name + " (copy)");
        payload.put("description", data.containsKey("description") ? data.get("description") : source.description);
        payload.put("currency", data.containsKey("currency") ? data.get("currency") : source.currency);
        payload.put("total_amount", data.containsKey("total_amount") ? data.get("total_amount") : source.totalAmount);
        payload.put("status", data.getOrDefault("status", PersonalBudget.DRAFT));
        payload.put("project_tag", data.containsKey("project_tag") ? data.get("project_tag") : source.projectTag);
        payload.put("notes", data.containsKey("notes") ? data.get("notes") : source.notes);
        payload.put("is_default", false);
        List<Map<String, Object>> cats = new ArrayList<>();
        for (PersonalBudgetCategory c : categories.listByBudget(source.id)) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("name", c.name);
            m.put("allocated_amount", c.allocatedAmount);
            m.put("order", c.order);
            m.put("notes", c.notes);
            m.put("group_id", c.groupId == null ? "" : c.groupId);
            m.put("category_id", c.categoryId == null ? "" : c.categoryId);
            m.put("parent_id", c.parentId == null ? "" : c.parentId);
            cats.add(m);
        }
        payload.put("categories", cats);
        // Dates the request does not send are copied from the source budget.
        return create(userId, payload,
                data.containsKey("start_date") ? start : source.startDate,
                data.containsKey("end_date") ? end : source.endDate);
    }

    public List<Map<String, Object>> budgetTransactions(String userId, String budgetId, int limit) {
        access.requireView(userId, budgetId);
        List<Map<String, Object>> out = new ArrayList<>();
        for (Transaction t : transactions.listByBudget(budgetId, 2000)) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", t.id);
            m.put("date", Py.isoformat(t.date));
            m.put("description", t.description);
            m.put("amount", Py.dec(t.amount));
            m.put("currency", t.currency);
            m.put("direction", t.direction);
            m.put("budget_category_id", t.budgetCategoryId == null ? "" : t.budgetCategoryId);
            m.put("note", t.note == null ? "" : t.note);
            out.add(m);
            if (out.size() >= limit) {
                break;
            }
        }
        return out;
    }

    public Map<String, Object> detail(String userId, String budgetId) {
        PersonalBudgetAccess.Access a = access.requireView(userId, budgetId);
        Map<String, Object> data = summary(a.budget(), userId, true, a.role());
        data.put("transactions", budgetTransactions(userId, budgetId, 50));
        data.put("can_edit", PersonalBudgetAccess.canEdit(a.role()));
        data.put("can_share", PersonalBudgetMember.OWNER.equals(a.role()));
        return data;
    }

    public void delete(String userId, String budgetId) {
        PersonalBudget b = access.requireOwner(userId, budgetId);
        if (b.isDefault) {
            throw new PersonalBudgetAccess.Invalid("Cannot delete the default budget.");
        }
        for (PersonalBudgetCategory c : categories.listByBudget(budgetId)) {
            categories.delete(c);
        }
        budgets.delete(b);
    }

    /** PATCH of one category line. */
    public Map<String, Object> updateCategory(String userId, String budgetId, String catId, Map<String, Object> data) {
        PersonalBudget budget = access.requireEdit(userId, budgetId).budget();
        PersonalBudgetCategory cat = categories.get(catId).filter(c -> budgetId.equals(c.budgetId))
                .orElseThrow(() -> new CategoryMissing());
        if (data.containsKey("name")) {
            String n = strip(data.get("name"));
            cat.name = n.isEmpty() ? cat.name : n;
        }
        if (data.containsKey("allocated_amount")) {
            Object raw = data.get("allocated_amount");
            try {
                cat.allocatedAmount = new BigDecimal(Py.truthy(raw) ? Py.str(raw).strip() : "0");
            } catch (NumberFormatException e) {
                throw new PersonalBudgetAccess.Invalid("A valid number is required.");
            }
        }
        if (data.containsKey("order")) {
            cat.order = intOr(data.get("order"), 0);
        }
        if (data.containsKey("notes")) {
            cat.notes = Py.truthy(data.get("notes")) ? Py.str(data.get("notes")) : "";
        }
        if (data.containsKey("group_id")) {
            cat.groupId = strip(data.get("group_id"));
        }
        if (data.containsKey("category_id")) {
            cat.categoryId = strip(data.get("category_id"));
        }
        if (data.containsKey("parent_id")) {
            cat.parentId = strip(data.get("parent_id"));
        }
        categories.save(cat);
        return summary(budget, userId, true, null);
    }

    public Map<String, Object> deleteCategory(String userId, String budgetId, String catId) {
        PersonalBudget budget = access.requireEdit(userId, budgetId).budget();
        PersonalBudgetCategory cat = categories.get(catId).filter(c -> budgetId.equals(c.budgetId))
                .orElseThrow(() -> new CategoryMissing());
        categories.delete(cat);
        for (PersonalBudgetCategory child : categories.listByBudget(budgetId)) {
            if (catId.equals(child.parentId)) {
                categories.delete(child);
            }
        }
        return summary(budget, userId, true, null);
    }

    /** The category line does not belong to the budget (404 "Category not found."). */
    public static class CategoryMissing extends RuntimeException {
        public CategoryMissing() {
            super("Category not found.");
        }
    }
}
