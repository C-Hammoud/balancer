package com.financetracker.finance.web;

import static com.financetracker.finance.web.FinanceJson.dec;
import static com.financetracker.finance.web.FinanceJson.uid;

import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.http.HttpStatus;
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

import com.financetracker.finance.application.AlertService;
import com.financetracker.finance.application.CategoryAccess;
import com.financetracker.finance.application.ReportService;
import com.financetracker.finance.domain.Account;
import com.financetracker.finance.domain.BudgetThreshold;
import com.financetracker.finance.domain.Category;
import com.financetracker.finance.domain.CategoryGroup;
import com.financetracker.finance.domain.FinanceRepositories.AccountRepository;
import com.financetracker.finance.domain.FinanceRepositories.BudgetThresholdRepository;
import com.financetracker.finance.domain.FinanceRepositories.MerchantLinkRepository;
import com.financetracker.finance.domain.FinanceRepositories.TypeCategoryMapRepository;
import com.financetracker.finance.domain.MerchantLink;
import com.financetracker.finance.domain.TypeCategoryMap;
import com.financetracker.shared.error.ApiException;
import com.financetracker.shared.locale.LocaleConstants;
import com.financetracker.shared.web.Field;
import com.financetracker.shared.web.RequestData;

/** Accounts (alias income-sources), merchant links, type maps and alert thresholds. */
@RestController
@RequestMapping("/api/v1/budgeting/config")
class ConfigController {

    private static final List<String> ACCOUNT_TYPES = List.of("bank", "credit_card", "wallet", "other");

    private final AccountRepository accounts;
    private final MerchantLinkRepository merchantLinks;
    private final TypeCategoryMapRepository typeMaps;
    private final BudgetThresholdRepository thresholds;
    private final CategoryAccess categoryAccess;
    private final ReportService reports;
    private final AlertService alerts;

    ConfigController(AccountRepository accounts, MerchantLinkRepository merchantLinks, TypeCategoryMapRepository typeMaps,
            BudgetThresholdRepository thresholds, CategoryAccess categoryAccess, ReportService reports, AlertService alerts) {
        this.accounts = accounts;
        this.merchantLinks = merchantLinks;
        this.typeMaps = typeMaps;
        this.thresholds = thresholds;
        this.categoryAccess = categoryAccess;
        this.reports = reports;
        this.alerts = alerts;
    }

    // ---------------------------------------------------------------- accounts

    private void clearExpenseDefaults(String uid, String exceptId) {
        for (Account a : accounts.listByUser(uid, false)) {
            if (exceptId != null && exceptId.equals(a.id)) {
                continue;
            }
            if (a.defaultForExpenses) {
                a.defaultForExpenses = false;
                accounts.save(a);
            }
        }
    }

    @GetMapping({"/accounts/", "/income-sources/"})
    List<Map<String, Object>> listAccounts(@RequestParam(required = false) String active) {
        return accounts.listByUser(uid(), "1".equals(active)).stream().map(FinanceJson::account).toList();
    }

    @PostMapping({"/accounts/", "/income-sources/"})
    ResponseEntity<Map<String, Object>> createAccount(@RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        RequestData d = RequestData.of(body);
        String name = d.string("name", Field.required().maxLength(120));
        String type = d.choice("account_type", ACCOUNT_TYPES, Field.withDefault("bank"));
        Integer order = d.integer("order", Field.withDefault(0));
        Boolean active = d.bool("is_active", Field.withDefault(true));
        Boolean isDefault = d.bool("is_default_for_expenses", Field.withDefault(false));
        d.validate();
        if (accounts.listByUser(uid, false).stream().anyMatch(a -> a.name.equalsIgnoreCase(name))) {
            throw ApiException.field("name", "An account with this name already exists.");
        }
        Account a = new Account();
        a.userId = uid;
        a.name = name;
        a.accountType = type;
        a.order = order;
        a.active = active;
        a.defaultForExpenses = isDefault;
        if (a.defaultForExpenses) {
            clearExpenseDefaults(uid, null);
        } else if (accounts.listByUser(uid, false).stream().noneMatch(x -> x.defaultForExpenses)) {
            a.defaultForExpenses = true;
        }
        accounts.save(a);
        return ResponseEntity.status(HttpStatus.CREATED).body(FinanceJson.account(a));
    }

    private Account ownedAccount(String uid, String pk) {
        return accounts.get(pk).filter(a -> uid.equals(a.userId)).orElseThrow(ApiException::notFound);
    }

    @PatchMapping({"/accounts/{pk}/", "/income-sources/{pk}/"})
    Map<String, Object> updateAccount(@PathVariable String pk, @RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        Account a = ownedAccount(uid, pk);
        RequestData d = RequestData.partial(body);
        String name = d.string("name", Field.required().maxLength(120));
        String type = d.choice("account_type", ACCOUNT_TYPES, Field.withDefault("bank"));
        Integer order = d.integer("order", Field.withDefault(0));
        Boolean active = d.bool("is_active", Field.withDefault(true));
        Boolean isDefault = d.bool("is_default_for_expenses", Field.withDefault(false));
        d.validate();
        if (d.provided("name")) {
            if (accounts.listByUser(uid, false).stream().anyMatch(x -> !x.id.equals(pk) && x.name.equalsIgnoreCase(name))) {
                throw ApiException.field("name", "An account with this name already exists.");
            }
            a.name = name;
        }
        if (d.provided("account_type")) {
            a.accountType = type;
        }
        if (d.provided("order")) {
            a.order = order;
        }
        if (d.provided("is_active")) {
            a.active = active;
            if (!a.active) {
                a.defaultForExpenses = false;
            }
        }
        if (d.provided("is_default_for_expenses")) {
            a.defaultForExpenses = isDefault;
            if (a.defaultForExpenses) {
                clearExpenseDefaults(uid, pk);
            }
        }
        accounts.save(a);
        return FinanceJson.account(a);
    }

    @DeleteMapping({"/accounts/{pk}/", "/income-sources/{pk}/"})
    ResponseEntity<Void> deleteAccount(@PathVariable String pk) {
        accounts.delete(ownedAccount(uid(), pk));
        return ResponseEntity.noContent().build();
    }

    // ---------------------------------------------------------------- merchant links

    @GetMapping("/merchant-links/")
    List<Map<String, Object>> listLinks() {
        String uid = uid();
        CategoryAccess.Visible visible = categoryAccess.forUser(uid);
        Map<String, CategoryGroup> groups = new LinkedHashMap<>();
        visible.groups().forEach(g -> groups.put(g.id, g));
        List<Map<String, Object>> out = new ArrayList<>();
        for (MerchantLink link : merchantLinks.findByUserIdOrderByIdAsc(uid)) {
            Category cat = visible.categoriesById().get(link.categoryId);
            String groupId = "";
            String groupName = "";
            String categoryName = "";
            if (cat != null) {
                categoryName = cat.name;
                groupId = cat.groupId == null ? "" : cat.groupId;
                CategoryGroup g = groups.get(groupId);
                groupName = g != null ? g.name : cat.groupName;
            }
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", link.id);
            m.put("keyword", link.keyword);
            m.put("category_id", link.categoryId);
            m.put("category_name", categoryName);
            m.put("group_id", groupId);
            m.put("group_name", groupName);
            out.add(m);
        }
        return out;
    }

    @PostMapping("/merchant-links/")
    ResponseEntity<Map<String, Object>> createLink(@RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        RequestData d = RequestData.of(body);
        String keyword = d.string("keyword", Field.required().maxLength(120));
        String categoryId = d.string("category_id", Field.required());
        List<String> transactionIds = d.stringList("transaction_ids", Field.withDefault(List.of()));
        Boolean applyUnmatched = d.bool("apply_unmatched", Field.withDefault(true));
        d.validate();
        if (categoryAccess.visibleCategory(uid, categoryId).isEmpty()) {
            throw ApiException.field("category_id", CategoriesController.categoryIdError(categoryAccess, uid, categoryId));
        }
        Optional<MerchantLink> existing = merchantLinks.findByUserIdOrderByIdAsc(uid).stream()
                .filter(l -> l.keyword.equalsIgnoreCase(keyword)).findFirst();
        MerchantLink link;
        boolean created;
        if (existing.isPresent()) {
            link = existing.get();
            link.categoryId = categoryId;
            link.keyword = keyword;
            created = false;
        } else {
            link = new MerchantLink();
            link.keyword = keyword;
            link.categoryId = categoryId;
            link.userId = uid;
            created = true;
        }
        merchantLinks.save(link);
        int updated = 0;
        if (applyUnmatched) {
            updated = reports.applyMerchantLink(uid, keyword, categoryId,
                    transactionIds == null || transactionIds.isEmpty() ? null : transactionIds);
            alerts.trigger(uid, null, null);
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("id", link.id);
        out.put("created", created);
        out.put("transactions_updated", updated);
        return ResponseEntity.status(created ? HttpStatus.CREATED : HttpStatus.OK).body(out);
    }

    @DeleteMapping("/merchant-links/{pk}/")
    ResponseEntity<Void> deleteLink(@PathVariable String pk) {
        String uid = uid();
        MerchantLink link = merchantLinks.get(pk).filter(l -> uid.equals(l.userId)).orElseThrow(ApiException::notFound);
        merchantLinks.delete(link);
        return ResponseEntity.noContent().build();
    }

    // ---------------------------------------------------------------- type maps

    @GetMapping("/type-maps/")
    List<Map<String, Object>> listTypeMaps() {
        String uid = uid();
        Map<String, String> effective = typeMaps.mapForUser(uid);
        Map<String, Category> categories = new LinkedHashMap<>();
        categoryAccess.visibleCategories(uid).forEach(c -> categories.put(c.id, c));
        Map<String, CategoryGroup> groups = new LinkedHashMap<>();
        categoryAccess.visibleGroups(uid).forEach(g -> groups.put(g.id, g));
        List<Map<String, Object>> out = new ArrayList<>();
        for (LocaleConstants.Choice type : LocaleConstants.CONSUMPTION_TYPES) {
            String ctype = type.code();
            String catId = effective.get(ctype);
            Category cat = catId == null ? null : categories.get(catId);
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("consumption_type", ctype);
            m.put("category_id", catId == null ? "" : catId);
            m.put("category_name", cat != null ? cat.name : "");
            m.put("group_id", cat != null ? cat.groupId : "");
            m.put("group_name", cat != null && groups.containsKey(cat.groupId) ? groups.get(cat.groupId).name : "");
            out.add(m);
        }
        return out;
    }

    @PostMapping("/type-maps/")
    ResponseEntity<Map<String, Object>> setTypeMap(@RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        RequestData d = RequestData.of(body);
        String ctype = d.choice("consumption_type",
                LocaleConstants.CONSUMPTION_TYPES.stream().map(LocaleConstants.Choice::code).toList(), Field.required());
        String categoryId = d.string("category_id", Field.required());
        d.validate();
        if (categoryAccess.visibleCategory(uid, categoryId).isEmpty()) {
            throw ApiException.field("category_id", "Subcategory not found.");
        }
        Optional<TypeCategoryMap> existing = typeMaps.findByUserIdOrderByIdAsc(uid).stream()
                .filter(m -> ctype.equals(m.consumptionType)).findFirst();
        if (existing.isPresent()) {
            existing.get().categoryId = categoryId;
            typeMaps.save(existing.get());
            return ResponseEntity.ok(Map.of("id", existing.get().id));
        }
        TypeCategoryMap m = new TypeCategoryMap();
        m.userId = uid;
        m.consumptionType = ctype;
        m.categoryId = categoryId;
        typeMaps.save(m);
        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("id", m.id));
    }

    // ---------------------------------------------------------------- thresholds

    @GetMapping("/thresholds/")
    List<Map<String, Object>> listThresholds() {
        String uid = uid();
        Map<String, Category> categories = new LinkedHashMap<>();
        categoryAccess.visibleCategories(uid).forEach(c -> categories.put(c.id, c));
        List<Map<String, Object>> out = new ArrayList<>();
        for (BudgetThreshold t : thresholds.findByUserIdOrderByIdAsc(uid)) {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("id", t.id);
            m.put("category_id", t.categoryId);
            m.put("category_name", t.categoryId != null && categories.containsKey(t.categoryId)
                    ? categories.get(t.categoryId).name : "Global default");
            m.put("warn_pct", t.warnPct);
            m.put("critical_pct", t.criticalPct);
            m.put("email_enabled", t.emailEnabled);
            out.add(dec(m));
        }
        return out;
    }

    /** Create or update the threshold for exactly this category (null = the global default). */
    @PostMapping("/thresholds/")
    ResponseEntity<Map<String, Object>> setThreshold(@RequestBody(required = false) Map<String, Object> body) {
        String uid = uid();
        RequestData d = RequestData.of(body);
        String categoryRaw = d.string("category_id", Field.optional().allowNull().allowBlank());
        BigDecimal warn = d.decimal("warn_pct", Field.withDefault(new BigDecimal("80")).digits(5, 1));
        BigDecimal critical = d.decimal("critical_pct", Field.withDefault(new BigDecimal("100")).digits(5, 1));
        Boolean email = d.bool("email_enabled", Field.withDefault(true));
        d.validate();
        if (warn != null && critical != null && warn.compareTo(critical) > 0) {
            throw ApiException.field("warn_pct", "Warn must be <= critical.");
        }
        String catId = categoryRaw == null || categoryRaw.strip().isEmpty() ? null : categoryRaw.strip();
        Optional<BudgetThreshold> existing = thresholds.getExact(uid, catId);
        if (existing.isPresent()) {
            BudgetThreshold t = existing.get();
            t.warnPct = warn;
            t.criticalPct = critical;
            t.emailEnabled = email;
            thresholds.save(t);
            return ResponseEntity.ok(Map.of("id", t.id));
        }
        BudgetThreshold t = new BudgetThreshold();
        t.userId = uid;
        t.categoryId = catId;
        t.warnPct = warn;
        t.criticalPct = critical;
        t.emailEnabled = email;
        thresholds.save(t);
        return ResponseEntity.status(HttpStatus.CREATED).body(Map.of("id", t.id));
    }

    @DeleteMapping("/thresholds/{pk}/")
    ResponseEntity<Void> deleteThreshold(@PathVariable String pk) {
        String uid = uid();
        BudgetThreshold t = thresholds.get(pk).filter(x -> uid.equals(x.userId)).orElseThrow(ApiException::notFound);
        thresholds.delete(t);
        return ResponseEntity.noContent().build();
    }
}
