package com.financetracker.finance;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;

import com.financetracker.ApiTestSupport;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.notifications.api.InAppNotifications;

/** Port of BE/tests/test_plan_api.py. */
class PlanApiTest extends ApiTestSupport {

    @Autowired
    InAppNotifications inbox;

    UserAccount user;
    Api api;
    String home;
    String fun;
    String stream;

    @BeforeEach
    void ready() {
        user = makeUser();
        api = api(user);
        home = createCategory(api, "Home", "Rent")[0];
        fun = createCategory(api, "Fun", "Movies")[0];
        Response r = api.post(B + "/income-streams/", m("name", "Salary", "amount", "4000", "currency", "USD"));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(201);
        stream = r.str("id");
    }

    @Test
    void incomeStreamCrudAndValidation() {
        Response r = api.post(B + "/income-streams/", m("name", "Freelance", "amount", "600", "currency", "USD",
                "frequency", "biweekly"));
        assertThat(r.str("monthly_amount")).isEqualTo("1300.00");
        Response body = api.get(B + "/income-streams/");
        assertThat((List<?>) body.get("streams")).hasSize(2);
        assertThat(body.str("monthly_total")).isEqualTo("5300.00");
        assertThat(api.post(B + "/income-streams/", m("name", "", "amount", "-1")).status()).isEqualTo(400);
        assertThat(api.patch(B + "/income-streams/" + stream + "/", m("amount", "4500")).str("amount")).isEqualTo("4500");
        assertThat(api.delete(B + "/income-streams/" + stream + "/").status()).isEqualTo(204);
    }

    @Test
    void bucketsDefaultAndUpdate() {
        Map<Object, Map<String, Object>> rows = api.get(B + "/plans/buckets/").list().stream()
                .collect(Collectors.toMap(r -> r.get("group_name"), r -> r));
        assertThat(rows.get("Home")).containsEntry("bucket", "needs").containsEntry("is_default", true);
        assertThat(rows.get("Fun")).containsEntry("bucket", "wants");
        Response r = api.put(B + "/plans/buckets/", m("buckets", m(fun, "needs")));
        assertThat(r.list().stream().filter(x -> "Fun".equals(x.get("group_name"))).findFirst().orElseThrow().get("bucket"))
                .isEqualTo("needs");
        assertThat(api.put(B + "/plans/buckets/", m("buckets", m(fun, "luxury"))).status()).isEqualTo(400);
    }

    @Test
    @SuppressWarnings("unchecked")
    void previewReturnsBothPlanTypes() {
        Response body = api.post(B + "/plans/preview/", m("year", 2026, "month", 11));
        List<Map<String, Object>> plans = (List<Map<String, Object>>) body.get("plans");
        assertThat(plans.stream().map(p -> p.get("plan_type")).toList()).containsExactly("rule_50_30_20", "spending_based");
        assertThat(plans.get(0).get("savings_amount")).isEqualTo("800.00");
    }

    @Test
    @SuppressWarnings("unchecked")
    void suggestEditAcceptFlow() {
        Response r = api.post(B + "/plans/", m("year", 2026, "month", 11, "plan_type", "rule_50_30_20"));
        assertThat(r.status()).isEqualTo(201);
        assertThat(r.str("status")).isEqualTo("suggested");
        String pid = r.str("id");
        r = api.patch(B + "/plans/" + pid + "/", m("amounts", m(fun, "1000")));
        assertThat(r.str("savings_amount")).isEqualTo("1000.00");
        r = api.post(B + "/plans/" + pid + "/accept/");
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.str("status")).isEqualTo("accepted");
        List<Map<String, Object>> rows = (List<Map<String, Object>>) api.get(B + "/budgets/", "year", "2026", "month", "11").get("rows");
        assertThat(rows.stream().filter(x -> "Fun".equals(x.get("category_name"))).findFirst().orElseThrow().get("forecast"))
                .isEqualTo("1000.00");
        assertThat(api.get(B + "/savings/2026/11/").str("target")).isEqualTo("1000.00");
        assertThat(api.patch(B + "/plans/" + pid + "/", m("amounts", m(fun, "5"))).status()).isEqualTo(400);
    }

    @Test
    void dismissedPlanCannotBeAccepted() {
        String pid = api.post(B + "/plans/", m("year", 2026, "month", 11)).str("id");
        assertThat(api.post(B + "/plans/" + pid + "/dismiss/").str("status")).isEqualTo("dismissed");
        assertThat(api.post(B + "/plans/" + pid + "/accept/").status()).isEqualTo(400);
    }

    @Test
    void otherUsersCannotTouchPlansStreamsOrNotifications() {
        Api other = api(makeUser());
        String pid = api.post(B + "/plans/", m("year", 2026, "month", 11)).str("id");
        String n = inbox.notify(user.userId(), "plan_suggested", "t", "", "", "", "fp-other");
        assertThat(other.get(B + "/plans/" + pid + "/").status()).isEqualTo(404);
        assertThat(other.post(B + "/plans/" + pid + "/accept/").status()).isEqualTo(404);
        assertThat(other.delete(B + "/income-streams/" + stream + "/").status()).isEqualTo(404);
        assertThat(other.post("/api/v1/notifications/" + n + "/read/").status()).isEqualTo(404);
        assertThat(other.get(B + "/plans/").list()).isEmpty();
    }

    @Test
    void notificationsReadFlow() {
        for (int i = 0; i < 3; i++) {
            inbox.notify(user.userId(), "plan_suggested", "n" + i, "", "", "", "fp" + i);
        }
        assertThat(api.get("/api/v1/notifications/count/").get("unread")).isEqualTo(3);
        String first = (String) api.get("/api/v1/notifications/").list().get(0).get("id");
        api.post("/api/v1/notifications/" + first + "/read/");
        assertThat(api.get("/api/v1/notifications/count/").get("unread")).isEqualTo(2);
        assertThat(api.post("/api/v1/notifications/read-all/").get("marked")).isEqualTo(2);
        assertThat(api.get("/api/v1/notifications/", "unread", "1").list()).isEmpty();
    }

    @Test
    void profilePlanSettings() {
        assertThat(api.patch("/api/v1/auth/me/", m("savings_target_pct", 95, "notify_plan_updates", false)).status()).isEqualTo(200);
        Response me = api.get("/api/v1/auth/me/");
        assertThat(me.get("savings_target_pct")).isEqualTo(90);
        assertThat(me.get("notify_plan_updates")).isEqualTo(false);
    }
}
