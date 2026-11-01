package com.financetracker.finance.web;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
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

import com.financetracker.finance.application.CategoryAccess;
import com.financetracker.finance.domain.Category;
import com.financetracker.finance.domain.CategoryGroup;
import com.financetracker.finance.domain.FinanceRepositories.CategoryRepository;
import com.financetracker.finance.domain.FinanceRepositories.GroupRepository;
import com.financetracker.finance.domain.FinanceRepositories.TypeCategoryMapRepository;
import com.financetracker.finance.domain.TypeCategoryMap;
import com.financetracker.shared.error.ApiException;
import com.financetracker.shared.security.AuthUser;
import com.financetracker.shared.security.CurrentUser;
import com.financetracker.shared.web.Field;
import com.financetracker.shared.web.RequestData;

/** Parent categories (groups) and subcategories; shared defaults are read-only for normal users. */
@RestController
@RequestMapping("/api/v1/budgeting")
class CategoriesController {

    static final String READ_ONLY_SHARED = "Shared default categories can only be changed by an administrator.";

    private final CategoryAccess access;
    private final GroupRepository groups;
    private final CategoryRepository categories;
    private final TypeCategoryMapRepository typeMaps;

    CategoriesController(CategoryAccess access, GroupRepository groups, CategoryRepository categories,
            TypeCategoryMapRepository typeMaps) {
        this.access = access;
        this.groups = groups;
        this.categories = categories;
        this.typeMaps = typeMaps;
    }

    private static Map<String, Object> ownership(String owner, AuthUser user) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("is_shared", owner == null || owner.isEmpty());
        m.put("can_edit", CategoryAccess.canEdit(owner, user));
        return m;
    }

    static Map<String, Object> groupJson(CategoryGroup g, AuthUser user) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", g.id);
        m.put("name", g.name);
        m.put("order", g.order);
        if (user != null) {
            m.putAll(ownership(g.userId, user));
        }
        return m;
    }

    static Map<String, Object> categoryJson(Category c, String groupName, AuthUser user) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", c.id);
        m.put("name", c.name);
        m.put("group_id", c.groupId);
        m.put("group_name", groupName);
        m.put("include_in_reports", c.includeInReports);
        m.put("order", c.order);
        if (user != null) {
            m.putAll(ownership(c.userId, user));
        }
        return m;
    }

    /** Staff may create shared defaults with {"shared": true}. */
    private static boolean wantsShared(Map<String, Object> body, AuthUser user) {
        Object flag = body == null ? null : body.get("shared");
        boolean on = Boolean.TRUE.equals(flag) || "true".equals(flag) || "1".equals(flag)
                || (flag instanceof Number n && n.doubleValue() == 1d);
        return on && user.staff();
    }

    private static Comparator<CategoryGroup> groupOrder() {
        return Comparator.comparingInt((CategoryGroup g) -> g.order).thenComparing(g -> g.name.toLowerCase(Locale.ROOT));
    }

    private static Comparator<Category> categoryOrder() {
        return Comparator.comparingInt((Category c) -> c.order).thenComparing(c -> c.name.toLowerCase(Locale.ROOT));
    }

    @GetMapping("/categories/")
    Map<String, Object> categoryGroups() {
        AuthUser user = CurrentUser.require();
        CategoryAccess.Visible visible = access.forUser(user.userId());
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("groups", visible.groups().stream().map(g -> groupJson(g, user)).toList());
        out.put("categories", visible.categoriesById().values().stream()
                .map(c -> categoryJson(c, c.groupName, user)).toList());
        return out;
    }

    // ---------------------------------------------------------------- groups

    @GetMapping("/config/groups/")
    List<Map<String, Object>> listGroups() {
        AuthUser user = CurrentUser.require();
        List<CategoryGroup> list = new ArrayList<>(access.visibleGroups(user.userId()));
        list.sort(groupOrder());
        return list.stream().map(g -> groupJson(g, user)).toList();
    }

    @PostMapping("/config/groups/")
    ResponseEntity<Map<String, Object>> createGroup(@RequestBody(required = false) Map<String, Object> body) {
        AuthUser user = CurrentUser.require();
        RequestData d = RequestData.of(body);
        String name = d.string("name", Field.required().maxLength(120));
        Integer order = d.integer("order", Field.withDefault(0));
        d.validate();
        boolean clash = access.visibleGroups(user.userId()).stream().anyMatch(g -> g.name.equalsIgnoreCase(name));
        if (clash) {
            throw ApiException.field("name", "A category with this name already exists.");
        }
        CategoryGroup g = new CategoryGroup();
        g.name = name;
        g.order = order;
        g.userId = wantsShared(body, user) ? "" : user.userId();
        groups.save(g);
        return ResponseEntity.status(HttpStatus.CREATED).body(groupJson(g, user));
    }

    private CategoryGroup editableGroup(AuthUser user, String pk) {
        CategoryGroup g = access.visibleGroup(user.userId(), pk).orElseThrow(ApiException::notFound);
        if (!CategoryAccess.canEdit(g.userId, user)) {
            throw ApiException.forbidden(READ_ONLY_SHARED);
        }
        return g;
    }

    @PatchMapping("/config/groups/{pk}/")
    Map<String, Object> updateGroup(@PathVariable String pk, @RequestBody(required = false) Map<String, Object> body) {
        AuthUser user = CurrentUser.require();
        CategoryGroup g = editableGroup(user, pk);
        RequestData d = RequestData.partial(body);
        String name = d.string("name", Field.required().maxLength(120));
        Integer order = d.integer("order", Field.withDefault(0));
        d.validate();
        if (d.provided("name")) {
            boolean clash = access.visibleGroups(user.userId()).stream()
                    .anyMatch(x -> !x.id.equals(pk) && x.name.equalsIgnoreCase(name));
            if (clash) {
                throw ApiException.field("name", "A category with this name already exists.");
            }
            g.name = name;
        }
        if (d.provided("order")) {
            g.order = order;
        }
        groups.save(g);
        return groupJson(g, user);
    }

    @DeleteMapping("/config/groups/{pk}/")
    ResponseEntity<Void> deleteGroup(@PathVariable String pk) {
        AuthUser user = CurrentUser.require();
        CategoryGroup g = editableGroup(user, pk);
        long children = categories.findAllByOrderByIdAsc().stream().filter(c -> pk.equals(c.groupId)).count();
        if (children > 0) {
            throw ApiException.badRequest("Remove or reassign " + children + " subcategory(ies) before deleting this category.");
        }
        groups.delete(g);
        return ResponseEntity.noContent().build();
    }

    // ---------------------------------------------------------------- subcategories

    @GetMapping("/config/categories/")
    List<Map<String, Object>> listCategories(@RequestParam(name = "group_id", required = false) String groupId) {
        AuthUser user = CurrentUser.require();
        Map<String, CategoryGroup> byId = new LinkedHashMap<>();
        access.visibleGroups(user.userId()).forEach(g -> byId.put(g.id, g));
        List<Category> cats = new ArrayList<>(access.visibleCategories(user.userId()));
        cats.sort(categoryOrder());
        String gid = groupId == null ? "" : groupId.strip();
        return cats.stream()
                .filter(c -> gid.isEmpty() || gid.equals(c.groupId))
                .map(c -> categoryJson(c, byId.containsKey(c.groupId) ? byId.get(c.groupId).name : "", user))
                .toList();
    }

    @PostMapping("/config/categories/")
    ResponseEntity<Map<String, Object>> createCategory(@RequestBody(required = false) Map<String, Object> body) {
        AuthUser user = CurrentUser.require();
        RequestData d = RequestData.of(body);
        String name = d.string("name", Field.required().maxLength(120));
        String groupId = d.string("group_id", Field.required());
        Boolean include = d.bool("include_in_reports", Field.withDefault(true));
        Integer order = d.integer("order", Field.withDefault(0));
        d.validate();
        CategoryGroup group = access.visibleGroup(user.userId(), groupId)
                .orElseThrow(() -> ApiException.field("group_id", "Parent category not found."));
        boolean clash = access.visibleCategories(user.userId()).stream()
                .anyMatch(c -> group.id.equals(c.groupId) && c.name.equalsIgnoreCase(name));
        if (clash) {
            throw ApiException.field("name", "A subcategory with this name already exists under this category.");
        }
        boolean shared = wantsShared(body, user) && (group.userId == null || group.userId.isEmpty());
        Category c = new Category();
        c.name = name;
        c.groupId = group.id;
        c.includeInReports = include;
        c.order = order;
        c.userId = shared ? "" : user.userId();
        categories.save(c);
        return ResponseEntity.status(HttpStatus.CREATED).body(categoryJson(c, group.name, user));
    }

    private Category editableCategory(AuthUser user, String pk) {
        Category c = access.visibleCategory(user.userId(), pk).orElseThrow(ApiException::notFound);
        if (!CategoryAccess.canEdit(c.userId, user)) {
            throw ApiException.forbidden(READ_ONLY_SHARED);
        }
        return c;
    }

    @PatchMapping("/config/categories/{pk}/")
    Map<String, Object> updateCategory(@PathVariable String pk, @RequestBody(required = false) Map<String, Object> body) {
        AuthUser user = CurrentUser.require();
        Category c = editableCategory(user, pk);
        RequestData d = RequestData.partial(body);
        String name = d.string("name", Field.required().maxLength(120));
        String groupId = d.string("group_id", Field.required());
        Boolean include = d.bool("include_in_reports", Field.withDefault(true));
        Integer order = d.integer("order", Field.withDefault(0));
        d.validate();
        if (d.provided("group_id")) {
            CategoryGroup group = access.visibleGroup(user.userId(), groupId)
                    .orElseThrow(() -> ApiException.field("group_id", "Parent category not found."));
            if ((c.userId == null || c.userId.isEmpty()) && group.userId != null && !group.userId.isEmpty()) {
                throw ApiException.field("group_id", "A shared subcategory cannot move under a personal category.");
            }
            c.groupId = group.id;
        }
        String groupName = groups.get(c.groupId).map(g -> g.name).orElse("");
        if (d.provided("name")) {
            boolean clash = access.visibleCategories(user.userId()).stream()
                    .anyMatch(x -> !x.id.equals(pk) && c.groupId.equals(x.groupId) && x.name.equalsIgnoreCase(name));
            if (clash) {
                throw ApiException.field("name", "A subcategory with this name already exists under this category.");
            }
            c.name = name;
        }
        if (d.provided("include_in_reports")) {
            c.includeInReports = include;
        }
        if (d.provided("order")) {
            c.order = order;
        }
        categories.save(c);
        return categoryJson(c, groupName, user);
    }

    @DeleteMapping("/config/categories/{pk}/")
    ResponseEntity<Void> deleteCategory(@PathVariable String pk) {
        AuthUser user = CurrentUser.require();
        Category c = editableCategory(user, pk);
        for (TypeCategoryMap m : typeMaps.findAllByOrderByIdAsc()) {
            if (pk.equals(m.categoryId)) {
                typeMaps.delete(m);
            }
        }
        categories.delete(c);
        return ResponseEntity.noContent().build();
    }

    /** _category_id_field_error: explains when a parent category was sent instead of a subcategory. */
    static String categoryIdError(CategoryAccess access, String userId, String categoryId) {
        Optional<CategoryGroup> g = access.visibleGroup(userId, categoryId);
        if (g.isPresent()) {
            List<Category> subs = new ArrayList<>(access.visibleCategories(userId).stream()
                    .filter(c -> g.get().id.equals(c.groupId)).toList());
            subs.sort(categoryOrder());
            if (!subs.isEmpty()) {
                String examples = String.join(", ", subs.stream().limit(6).map(c -> c.name).toList());
                return "\"" + g.get().name + "\" is a parent category, not a subcategory (merchant). Pick one under it, e.g. "
                        + examples + ".";
            }
            return "\"" + g.get().name + "\" is a parent category with no subcategories yet. "
                    + "Add merchants under Setup → Categories first.";
        }
        return "Subcategory id \"" + categoryId + "\" was not found. Choose a merchant (subcategory) under a parent category.";
    }
}
