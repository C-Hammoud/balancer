package com.financetracker.finance;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import com.financetracker.ApiTestSupport;
import com.financetracker.finance.domain.Category;
import com.financetracker.finance.domain.CategoryGroup;
import com.financetracker.finance.domain.FinanceRepositories.CategoryRepository;
import com.financetracker.finance.domain.FinanceRepositories.GroupRepository;

/** Port of BE/tests/test_categories.py (shared defaults read-only, private categories). */
class CategoriesTest extends ApiTestSupport {

    @Autowired
    GroupRepository groups;
    @Autowired
    CategoryRepository categories;

    CategoryGroup sharedGroup;
    Category sharedCategory;
    Api api;

    @BeforeEach
    void shared() {
        sharedGroup = new CategoryGroup();
        sharedGroup.name = "Home";
        groups.save(sharedGroup);
        sharedCategory = new Category();
        sharedCategory.name = "Rent";
        sharedCategory.groupId = sharedGroup.id;
        categories.save(sharedCategory);
        api = api(makeUser());
    }

    @Test
    void usersCannotChangeSharedDefaults() {
        assertThat(api.patch(B + "/config/groups/" + sharedGroup.id + "/", m("name", "Hacked")).status()).isEqualTo(403);
        assertThat(api.delete(B + "/config/categories/" + sharedCategory.id + "/").status()).isEqualTo(403);
        assertThat(api.patch(B + "/config/categories/" + sharedCategory.id + "/", m("name", "X")).status()).isEqualTo(403);
        assertThat(groups.findById(sharedGroup.id).orElseThrow().name).isEqualTo("Home");
    }

    @Test
    void staffCanChangeSharedDefaults() {
        Api admin = api(makeUser(true, "", ""));
        assertThat(admin.patch(B + "/config/groups/" + sharedGroup.id + "/", m("name", "House")).status()).isEqualTo(200);
        assertThat(groups.findById(sharedGroup.id).orElseThrow().name).isEqualTo("House");
    }

    @Test
    void categoriesArePrivatePerUser() {
        String[] ids = createCategory(api, "Hobbies", "Guitar");
        Api other = api(makeUser());
        @SuppressWarnings("unchecked")
        List<Map<String, Object>> theirs = (List<Map<String, Object>>) other.get(B + "/categories/").get("categories");
        List<Object> names = theirs.stream().map(x -> x.get("name")).toList();
        assertThat(names).doesNotContain("Guitar").contains("Rent");
        assertThat(other.patch(B + "/config/categories/" + ids[1] + "/", m("name", "Mine")).status()).isEqualTo(404);
        assertThat(other.delete(B + "/config/groups/" + ids[0] + "/").status()).isEqualTo(404);

        @SuppressWarnings("unchecked")
        Map<Object, Map<String, Object>> mine = ((List<Map<String, Object>>) api.get(B + "/categories/").get("categories"))
                .stream().collect(Collectors.toMap(x -> x.get("name"), x -> x));
        assertThat(mine.get("Guitar")).containsEntry("can_edit", true).containsEntry("is_shared", false);
        assertThat(mine.get("Rent")).containsEntry("can_edit", false).containsEntry("is_shared", true);
    }

    @Test
    void cannotUseAnotherUsersCategory() {
        String cid = createCategory(api, "Hobbies", "Guitar")[1];
        Api other = api(makeUser());
        String acc = createAccount(other);
        Response r = other.post(B + "/transactions/", m("date", "2026-10-01", "description", "x", "amount", "5",
                "direction", "expense", "category_id", cid, "account_id", acc));
        assertThat(r.status()).isEqualTo(400);
        assertThat(other.patch(B + "/budgets/2026/10/" + cid + "/", m("forecast", "10")).status()).isEqualTo(404);
    }

    @Test
    void userCanAddOwnSubcategoryUnderSharedGroup() {
        Response r = api.post(B + "/config/categories/", m("name", "Utilities", "group_id", sharedGroup.id));
        assertThat(r.status()).isEqualTo(201);
        assertThat(r.get("can_edit")).isEqualTo(true);
        addExpense(api, createAccount(api), r.str("id"), 10);
    }
}
