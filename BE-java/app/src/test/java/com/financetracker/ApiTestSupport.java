package com.financetracker;

import static org.assertj.core.api.Assertions.assertThat;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.BeforeEach;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.request.AbstractMockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders;
import org.springframework.test.web.servlet.request.MockMultipartHttpServletRequestBuilder;
import org.springframework.transaction.annotation.Transactional;

import com.financetracker.access.application.ProfileService;
import com.financetracker.access.domain.AccessRepositories.UserAccountRepository;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.access.security.DjangoPasswordHasher;
import com.financetracker.access.security.SimpleJwtTokens;
import com.financetracker.notifications.email.EmailDelivery;
import com.financetracker.shared.web.Throttler;

import tools.jackson.databind.json.JsonMapper;

/**
 * Test harness mirroring BE/tests/conftest.py and helpers.py: verified users with password
 * "S3cure-pass!", an authenticated API client per user, and the budgeting fixture helpers.
 * Each test runs in a transaction that is rolled back.
 */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
@Transactional
public abstract class ApiTestSupport {

    protected static final String B = "/api/v1/budgeting";
    protected static final String PASSWORD = "S3cure-pass!";
    protected static final JsonMapper JSON = JsonMapper.builder().build();
    private static final AtomicInteger COUNTER = new AtomicInteger();

    @Autowired
    protected MockMvc mvc;
    @Autowired
    protected UserAccountRepository users;
    @Autowired
    protected ProfileService profiles;
    @Autowired
    protected DjangoPasswordHasher hasher;
    @Autowired
    protected SimpleJwtTokens tokens;
    @Autowired
    protected Throttler throttler;
    /** Real delivery (console backend) that tests can inspect, like Django's mail.outbox. */
    @MockitoSpyBean
    protected EmailDelivery emailDelivery;

    @BeforeEach
    void resetThrottles() {
        throttler.reset();
    }

    // ---------------------------------------------------------------- users

    protected UserAccount makeUser() {
        return makeUser(false, "", "");
    }

    protected UserAccount makeUser(boolean staff, String firstName, String lastName) {
        String name = "user" + COUNTER.incrementAndGet() + "x" + System.nanoTime() % 100000;
        UserAccount u = new UserAccount();
        u.setUsername(name);
        u.setEmail(name + "@example.com");
        u.setFirstName(firstName);
        u.setLastName(lastName);
        u.setPassword(hasher.encode(PASSWORD));
        u.setStaff(staff);
        u.setDateJoined(Instant.now());
        users.save(u);
        profiles.markEmailVerified(u);
        return u;
    }

    protected Api api(UserAccount user) {
        return new Api(user == null ? null : "Bearer " + tokens.forUser(user).access());
    }

    protected Api anonymous() {
        return new Api(null);
    }

    // ---------------------------------------------------------------- client

    /** A JSON response: status plus the parsed body. */
    public record Response(int status, Object body) {

        @SuppressWarnings("unchecked")
        public Map<String, Object> map() {
            return (Map<String, Object>) body;
        }

        @SuppressWarnings("unchecked")
        public List<Map<String, Object>> list() {
            return (List<Map<String, Object>>) body;
        }

        public Object get(String key) {
            return map().get(key);
        }

        public String str(String key) {
            Object v = map().get(key);
            return v == null ? null : String.valueOf(v);
        }
    }

    public class Api {
        private final String auth;

        Api(String auth) {
            this.auth = auth;
        }

        private Response run(AbstractMockHttpServletRequestBuilder<?> req) {
            if (auth != null) {
                req.header("Authorization", auth);
            }
            try {
                MvcResult r = mvc.perform(req).andReturn();
                String text = r.getResponse().getContentAsString();
                Object body = text.isEmpty() || !text.trim().matches("^[\\[{].*")
                        ? text : JSON.readValue(text, Object.class);
                return new Response(r.getResponse().getStatus(), body);
            } catch (Exception e) {
                throw new IllegalStateException(e);
            }
        }

        private MockHttpServletRequestBuilder json(MockHttpServletRequestBuilder req, Object body) {
            return req.contentType(MediaType.APPLICATION_JSON).content(JSON.writeValueAsString(body == null ? Map.of() : body));
        }

        public Response get(String path, String... params) {
            MockHttpServletRequestBuilder req = MockMvcRequestBuilders.get(path);
            for (int i = 0; i + 1 < params.length; i += 2) {
                req.queryParam(params[i], params[i + 1]);
            }
            return run(req);
        }

        public Response post(String path, Object body) {
            return run(json(MockMvcRequestBuilders.post(path), body));
        }

        public Response post(String path) {
            return run(MockMvcRequestBuilders.post(path));
        }

        public Response patch(String path, Object body) {
            return run(json(MockMvcRequestBuilders.patch(path), body));
        }

        public Response put(String path, Object body) {
            return run(json(MockMvcRequestBuilders.put(path), body));
        }

        public Response delete(String path) {
            return run(MockMvcRequestBuilders.delete(path));
        }

        public Response upload(String path, String filename, byte[] content, String... fields) {
            MockMultipartHttpServletRequestBuilder req = MockMvcRequestBuilders.multipart(path).file(new MockMultipartFile("file", filename, null, content));
            for (int i = 0; i + 1 < fields.length; i += 2) {
                req.param(fields[i], fields[i + 1]);
            }
            return run(req);
        }
    }

    // ---------------------------------------------------------------- helpers.py

    protected static Map<String, Object> m(Object... kv) {
        Map<String, Object> out = new LinkedHashMap<>();
        for (int i = 0; i + 1 < kv.length; i += 2) {
            out.put((String) kv[i], kv[i + 1]);
        }
        return out;
    }

    /** create_category: returns {group_id, category_id}. */
    protected String[] createCategory(Api api, String groupName, String name) {
        Response g = api.post(B + "/config/groups/", m("name", groupName));
        assertThat(g.status()).as(String.valueOf(g.body())).isEqualTo(201);
        Response c = api.post(B + "/config/categories/", m("name", name, "group_id", g.str("id")));
        assertThat(c.status()).as(String.valueOf(c.body())).isEqualTo(201);
        return new String[] {g.str("id"), c.str("id")};
    }

    protected String[] createCategory(Api api) {
        return createCategory(api, "Food", "Groceries");
    }

    protected String createAccount(Api api, String name) {
        Response r = api.post(B + "/config/accounts/", m("name", name));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(201);
        return r.str("id");
    }

    protected String createAccount(Api api) {
        return createAccount(api, "Main bank");
    }

    protected void setBudget(Api api, String categoryId, Object amount, LocalDate d) {
        Response r = api.patch(String.format("%s/budgets/%d/%d/%s/", B, d.getYear(), d.getMonthValue(), categoryId),
                m("forecast", String.valueOf(amount)));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(200);
    }

    protected void setBudget(Api api, String categoryId, Object amount) {
        setBudget(api, categoryId, amount, LocalDate.now());
    }

    protected Map<String, Object> addExpense(Api api, String accountId, String categoryId, Object amount, LocalDate d) {
        Response r = api.post(B + "/transactions/", m("date", (d == null ? LocalDate.now() : d).toString(),
                "description", "Shop", "amount", String.valueOf(amount), "direction", "expense",
                "category_id", categoryId, "account_id", accountId));
        assertThat(r.status()).as(String.valueOf(r.body())).isEqualTo(201);
        return r.map();
    }

    protected Map<String, Object> addExpense(Api api, String accountId, String categoryId, Object amount) {
        return addExpense(api, accountId, categoryId, amount, null);
    }

    protected static void assertDec(Object actual, String expected) {
        assertThat(new BigDecimal(String.valueOf(actual))).isEqualByComparingTo(expected);
    }
}
