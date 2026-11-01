package com.financetracker.access;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.patch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.net.URI;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentCaptor;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import com.financetracker.notifications.api.EmailRecipient;
import com.financetracker.notifications.api.TransactionalEmails;
import com.financetracker.shared.web.Throttler;

import tools.jackson.databind.json.JsonMapper;

/** Register, verify, sign in, profile, refresh rotation and logout, with Django's response shapes. */
@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("test")
class AuthFlowIntegrationTest {

    private static final JsonMapper JSON = JsonMapper.builder().build();

    @Autowired
    MockMvc mvc;

    @Autowired
    Throttler throttler;

    @MockitoBean
    TransactionalEmails emails;

    @BeforeEach
    void setUp() {
        throttler.reset();
        when(emails.welcomeAndVerification(any(), anyString(), anyString())).thenReturn(true);
        when(emails.verification(any(), anyString(), anyString())).thenReturn(true);
    }

    private static String json(Object body) {
        return JSON.writeValueAsString(body);
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> body(MvcResult r) throws Exception {
        return JSON.readValue(r.getResponse().getContentAsString(), Map.class);
    }

    @Test
    void registerValidatesLikeDrf() throws Exception {
        mvc.perform(post("/api/v1/auth/register/").contentType(MediaType.APPLICATION_JSON).content("{}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.username[0]").value("This field is required."))
                .andExpect(jsonPath("$.password[0]").value("This field is required."))
                .andExpect(jsonPath("$.password_confirm[0]").value("This field is required."));

        mvc.perform(post("/api/v1/auth/register/").contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of("username", "bad name", "password", "1234", "password_confirm", "1234",
                                "email", "not-an-email"))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.username[0]").value(
                        "Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters."))
                .andExpect(jsonPath("$.email[0]").value("Enter a valid email address."))
                .andExpect(jsonPath("$.password[0]").value("This password is too short. It must contain at least 8 characters."))
                .andExpect(jsonPath("$.password[1]").value("This password is too common."))
                .andExpect(jsonPath("$.password[2]").value("This password is entirely numeric."));

        mvc.perform(post("/api/v1/auth/register/").contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of("username", "mismatch", "password", "Tr1cky-horse-77",
                                "password_confirm", "Tr1cky-horse-78"))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.password_confirm[0]").value("Passwords do not match."));
    }

    @Test
    void fullAuthenticationFlow() throws Exception {
        // Register: verification required, email sent with a working link.
        mvc.perform(post("/api/v1/auth/register/").contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of("username", "alice", "email", "Alice@Example.COM", "first_name", "Alice",
                                "password", "Tr1cky-horse-77", "password_confirm", "Tr1cky-horse-77"))))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.verification_required").value(true))
                .andExpect(jsonPath("$.email_sent").value(true))
                .andExpect(jsonPath("$.email").value("Alice@example.com"));

        ArgumentCaptor<String> verifyUrl = ArgumentCaptor.forClass(String.class);
        ArgumentCaptor<EmailRecipient> recipient = ArgumentCaptor.forClass(EmailRecipient.class);
        verify(emails).welcomeAndVerification(recipient.capture(), verifyUrl.capture(), anyString());
        assertThat(recipient.getValue().displayName("there")).isEqualTo("Alice");

        // Duplicate username.
        mvc.perform(post("/api/v1/auth/register/").contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of("username", "alice", "password", "Tr1cky-horse-77",
                                "password_confirm", "Tr1cky-horse-77"))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.username[0]").value("A user with that username already exists."));

        // Login is blocked until the email is verified (code is a plain string for the clients).
        String credentials = json(Map.of("username", "alice", "password", "Tr1cky-horse-77"));
        mvc.perform(post("/api/v1/auth/login/").contentType(MediaType.APPLICATION_JSON).content(credentials))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code").value("email_not_verified"));

        // Wrong password.
        mvc.perform(post("/api/v1/auth/login/").contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of("username", "alice", "password", "nope"))))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("No active account found with the given credentials"));

        // The emailed GET link verifies and hands off to the app.
        URI link = URI.create(verifyUrl.getValue());
        mvc.perform(get(link.getPath().replace("/api/v1", "/api/v1")).queryParam("uid", query(link, "uid"))
                        .queryParam("token", query(link, "token")))
                .andExpect(status().isOk())
                .andExpect(content().string(org.hamcrest.Matchers.containsString("Email verified")));

        MvcResult login = mvc.perform(post("/api/v1/auth/login/").contentType(MediaType.APPLICATION_JSON).content(credentials))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.refresh").isString())
                .andExpect(jsonPath("$.access").isString())
                .andReturn();
        String access = (String) body(login).get("access");
        String refresh = (String) body(login).get("refresh");

        // Profile.
        mvc.perform(get("/api/v1/auth/me/").header("Authorization", "Bearer " + access))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.username").value("alice"))
                .andExpect(jsonPath("$.email_verified").value(true))
                .andExpect(jsonPath("$.default_currency").value("USD"))
                .andExpect(jsonPath("$.setup_status").value("pending"))
                .andExpect(jsonPath("$.savings_target_pct").value(20));

        mvc.perform(patch("/api/v1/auth/me/").header("Authorization", "Bearer " + access)
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of("timezone", "Asia/Beirut", "default_currency", "LBP",
                                "setup_status", "incomplete", "savings_target_pct", 95, "notify_plan_updates", false))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.timezone").value("Asia/Beirut"))
                .andExpect(jsonPath("$.country").value("LB"))
                .andExpect(jsonPath("$.default_currency").value("LBP"))
                .andExpect(jsonPath("$.setup_status").value("incomplete"))
                .andExpect(jsonPath("$.savings_target_pct").value(90))
                .andExpect(jsonPath("$.notify_plan_updates").value(false));

        mvc.perform(patch("/api/v1/auth/me/").header("Authorization", "Bearer " + access)
                        .contentType(MediaType.APPLICATION_JSON).content(json(Map.of("default_currency", "EUR"))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.default_currency[0]").value("\"EUR\" is not a valid choice."));

        mvc.perform(get("/api/v1/meta/").header("Authorization", "Bearer " + access))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.currencies[0].code").value("USD"))
                .andExpect(jsonPath("$.countries[0].label").value("Lebanon"))
                .andExpect(jsonPath("$.saved_preferences.default_currency").value("LBP"))
                .andExpect(jsonPath("$.suggested.timezone").value("Asia/Beirut"));

        // Refresh rotates and blacklists the old refresh token.
        MvcResult refreshed = mvc.perform(post("/api/v1/auth/token/refresh/").contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of("refresh", refresh))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.access").isString())
                .andExpect(jsonPath("$.refresh").isString())
                .andReturn();
        mvc.perform(post("/api/v1/auth/token/refresh/").contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of("refresh", refresh))))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("Token is blacklisted"))
                .andExpect(jsonPath("$.code").value("token_not_valid"));

        // Logout revokes the rotated token.
        String rotated = (String) body(refreshed).get("refresh");
        mvc.perform(post("/api/v1/auth/logout/").contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of("refresh", rotated))))
                .andExpect(status().isNoContent());
        mvc.perform(post("/api/v1/auth/token/refresh/").contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of("refresh", rotated))))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("Token is blacklisted"));
    }

    @Test
    void authenticationErrorsMatchSimpleJwt() throws Exception {
        mvc.perform(get("/api/v1/auth/me/"))
                .andExpect(status().isUnauthorized())
                .andExpect(header().string("WWW-Authenticate", "Bearer realm=\"api\""))
                .andExpect(jsonPath("$.detail").value("Authentication credentials were not provided."));

        mvc.perform(get("/api/v1/auth/me/").header("Authorization", "Bearer not-a-token"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.detail").value("Given token not valid for any token type"))
                .andExpect(jsonPath("$.code").value("token_not_valid"))
                .andExpect(jsonPath("$.messages[0].token_class").value("AccessToken"))
                .andExpect(jsonPath("$.messages[0].message").value("Token is invalid"));

        mvc.perform(get("/api/v1/health/"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void loginIsThrottledPerClient() throws Exception {
        String credentials = json(Map.of("username", "nobody", "password", "x"));
        for (int i = 0; i < 10; i++) {
            mvc.perform(post("/api/v1/auth/login/").header("X-Forwarded-For", "203.0.113.9")
                            .contentType(MediaType.APPLICATION_JSON).content(credentials))
                    .andExpect(status().isUnauthorized());
        }
        mvc.perform(post("/api/v1/auth/login/").header("X-Forwarded-For", "203.0.113.9")
                        .contentType(MediaType.APPLICATION_JSON).content(credentials))
                .andExpect(status().isTooManyRequests())
                .andExpect(header().exists("Retry-After"))
                .andExpect(jsonPath("$.detail").value(org.hamcrest.Matchers.startsWith("Request was throttled. Expected available in ")));
    }

    @Test
    void passwordResetAlwaysAnswersTheSame() throws Exception {
        mvc.perform(post("/api/v1/auth/password-reset/").contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of("identifier", "nobody@example.com"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.detail").value(
                        "If an account exists with that email or username, you will receive password reset instructions shortly."));

        mvc.perform(post("/api/v1/auth/password-reset/confirm/").contentType(MediaType.APPLICATION_JSON)
                        .content(json(Map.of("uid", "NDI", "token", "abc-def", "password", "Tr1cky-horse-77",
                                "password_confirm", "Tr1cky-horse-77"))))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").value("Invalid or expired reset link."));
    }

    private static String query(URI uri, String name) {
        for (String pair : uri.getRawQuery().split("&")) {
            String[] kv = pair.split("=", 2);
            if (kv[0].equals(name)) {
                return java.net.URLDecoder.decode(kv[1], java.nio.charset.StandardCharsets.UTF_8);
            }
        }
        return null;
    }
}
