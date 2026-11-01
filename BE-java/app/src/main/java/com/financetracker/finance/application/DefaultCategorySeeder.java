package com.financetracker.finance.application;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

import com.financetracker.finance.domain.Category;
import com.financetracker.finance.domain.CategoryGroup;
import com.financetracker.finance.domain.FinanceRepositories.CategoryRepository;
import com.financetracker.finance.domain.FinanceRepositories.GroupRepository;
import com.financetracker.finance.domain.FinanceRepositories.TypeCategoryMapRepository;
import com.financetracker.finance.domain.TypeCategoryMap;

/**
 * seed_firestore_budgeting: shared default groups, subcategories and expense-type maps. Runs at
 * startup only when there are no groups at all (a fresh database), unless app.seed-defaults=false.
 */
@Component
class DefaultCategorySeeder implements ApplicationRunner {

    private static final Logger log = LoggerFactory.getLogger(DefaultCategorySeeder.class);

    private static final List<Object[]> GROUPS = List.of(
            new Object[] {"Home", 0}, new Object[] {"Food", 1}, new Object[] {"Transportation", 2},
            new Object[] {"Utilities", 3}, new Object[] {"Health", 4}, new Object[] {"Other", 5});

    /** (name, group, include_in_reports, order) */
    private static final List<Object[]> CATEGORIES = List.of(
            new Object[] {"Rent / Mortgage", "Home", true, 0},
            new Object[] {"Maintenance", "Home", true, 1},
            new Object[] {"Groceries", "Food", true, 0},
            new Object[] {"Restaurants", "Food", true, 1},
            new Object[] {"Fuel", "Transportation", true, 0},
            new Object[] {"Public transport", "Transportation", true, 1},
            new Object[] {"Electricity", "Utilities", true, 0},
            new Object[] {"Water", "Utilities", true, 1},
            new Object[] {"Insurance", "Health", true, 0},
            new Object[] {"Medical", "Health", true, 1},
            new Object[] {"Other", "Other", true, 0});

    /** consumption type -> (category, group) */
    private static final List<String[]> TYPE_MAPS = List.of(
            new String[] {"market", "Groceries", "Food"},
            new String[] {"food", "Restaurants", "Food"},
            new String[] {"transport", "Fuel", "Transportation"},
            new String[] {"other", "Other", "Other"});

    private final GroupRepository groups;
    private final CategoryRepository categories;
    private final TypeCategoryMapRepository typeMaps;
    private final boolean enabled;

    DefaultCategorySeeder(GroupRepository groups, CategoryRepository categories, TypeCategoryMapRepository typeMaps,
            @Value("${app.seed-defaults:true}") boolean enabled) {
        this.groups = groups;
        this.categories = categories;
        this.typeMaps = typeMaps;
        this.enabled = enabled;
    }

    @Override
    public void run(ApplicationArguments args) {
        if (!enabled || !groups.findAllByOrderByIdAsc().isEmpty()) {
            return;
        }
        Map<String, String> groupIds = new LinkedHashMap<>();
        for (Object[] g : GROUPS) {
            CategoryGroup group = new CategoryGroup();
            group.name = (String) g[0];
            group.order = (Integer) g[1];
            groups.save(group);
            groupIds.put(group.name, group.id);
        }
        Map<String, String> catIds = new LinkedHashMap<>();
        for (Object[] c : CATEGORIES) {
            Category cat = new Category();
            cat.name = (String) c[0];
            cat.groupId = groupIds.get((String) c[1]);
            cat.includeInReports = (Boolean) c[2];
            cat.order = (Integer) c[3];
            categories.save(cat);
            catIds.put(c[0] + "|" + c[1], cat.id);
        }
        for (String[] m : TYPE_MAPS) {
            TypeCategoryMap map = new TypeCategoryMap();
            map.userId = "";
            map.consumptionType = m[0];
            map.categoryId = catIds.get(m[1] + "|" + m[2]);
            typeMaps.save(map);
        }
        log.info("Seeded {} default groups, {} categories and {} type maps.", GROUPS.size(), CATEGORIES.size(), TYPE_MAPS.size());
    }
}
