package com.financetracker.finance.application;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Component;

import com.financetracker.finance.domain.Category;
import com.financetracker.finance.domain.CategoryGroup;
import com.financetracker.finance.domain.FinanceRepositories.CategoryRepository;
import com.financetracker.finance.domain.FinanceRepositories.GroupRepository;
import com.financetracker.shared.security.AuthUser;

/**
 * Port of budgeting/category_access.py: users see the shared defaults (no owner) plus their own;
 * only staff may change shared defaults.
 */
@Component
public class CategoryAccess {

    /** categories_and_groups_for_user: visible groups (store order) and categories by id. */
    public record Visible(List<CategoryGroup> groups, Map<String, Category> categoriesById) {
    }

    private final GroupRepository groups;
    private final CategoryRepository categories;

    public CategoryAccess(GroupRepository groups, CategoryRepository categories) {
        this.groups = groups;
        this.categories = categories;
    }

    public static boolean isVisible(String owner, String userId) {
        return owner == null || owner.isEmpty() || owner.equals(userId);
    }

    public static boolean canEdit(String owner, AuthUser user) {
        if (owner != null && !owner.isEmpty()) {
            return owner.equals(user.userId());
        }
        return user.staff();
    }

    public List<CategoryGroup> visibleGroups(String userId) {
        return groups.findAllByOrderByIdAsc().stream().filter(g -> isVisible(g.userId, userId)).toList();
    }

    public List<Category> visibleCategories(String userId) {
        return categories.findAllByOrderByIdAsc().stream().filter(c -> isVisible(c.userId, userId)).toList();
    }

    public Optional<CategoryGroup> visibleGroup(String userId, String pk) {
        return groups.get(pk).filter(g -> isVisible(g.userId, userId));
    }

    public Optional<Category> visibleCategory(String userId, String pk) {
        return categories.get(pk).filter(c -> isVisible(c.userId, userId));
    }

    public Visible forUser(String userId) {
        Map<String, CategoryGroup> byId = new LinkedHashMap<>();
        for (CategoryGroup g : visibleGroups(userId)) {
            byId.put(g.id, g);
        }
        Map<String, Category> cats = new LinkedHashMap<>();
        for (Category c : visibleCategories(userId)) {
            CategoryGroup g = c.groupId == null ? null : byId.get(c.groupId);
            c.groupName = g == null ? "" : g.name;
            cats.put(c.id, c);
        }
        return new Visible(List.copyOf(byId.values()), cats);
    }
}
