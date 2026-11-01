package com.financetracker.access;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;

import com.financetracker.ApiTestSupport;
import com.financetracker.access.application.AuthService;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.access.security.DjangoTokenGenerator;
import com.financetracker.shared.web.Py;

/** Port of BE/tests/test_auth_security.py. */
class AuthSecurityTest extends ApiTestSupport {

    static final String A = "/api/v1/auth";

    @Autowired
    AuthService auth;
    @Autowired
    @Qualifier("passwordResetTokens")
    DjangoTokenGenerator resetTokens;
    @Autowired
    @Qualifier("emailVerificationTokens")
    DjangoTokenGenerator verifyTokens;

    private static String uid(UserAccount u) {
        return Py.urlsafeB64Encode(String.valueOf(u.getId()));
    }

    @Test
    void verificationTokenCannotResetPassword() {
        UserAccount user = makeUser();
        Response r = anonymous().post(A + "/password-reset/confirm/", m("uid", uid(user), "token", verifyTokens.makeToken(user),
                "password", "N3w-strong-pass!", "password_confirm", "N3w-strong-pass!"));
        assertThat(r.status()).isEqualTo(400);
        assertThat(hasher.matches(PASSWORD, users.findById(user.getId()).orElseThrow().getPassword())).isTrue();
    }

    @Test
    void resetTokenCannotVerifyEmail() {
        UserAccount user = makeUser();
        assertThat(auth.verifyEmail(uid(user), resetTokens.makeToken(user)).ok()).isFalse();
    }

    @Test
    void verificationTokenVerifiesEmail() {
        UserAccount user = makeUser();
        assertThat(auth.verifyEmail(uid(user), verifyTokens.makeToken(user)).ok()).isTrue();
    }

    @Test
    void loginIsRateLimited() {
        UserAccount user = makeUser();
        Api client = anonymous();
        List<Integer> codes = new ArrayList<>();
        for (int i = 0; i < 12; i++) {
            codes.add(client.post(A + "/login/", m("username", user.getUsername(), "password", "wrong")).status());
        }
        assertThat(codes).contains(429);
        assertThat(codes.indexOf(429)).isEqualTo(10); // default 10/min
    }

    @Test
    void passwordResetIsRateLimited() {
        UserAccount user = makeUser();
        Api client = anonymous();
        List<Integer> codes = new ArrayList<>();
        for (int i = 0; i < 7; i++) {
            codes.add(client.post(A + "/password-reset/", m("identifier", user.getEmail())).status());
        }
        assertThat(codes.subList(0, 5)).containsOnly(200);
        assertThat(codes.get(5)).isEqualTo(429);
    }

    @Test
    void logoutRevokesRefreshToken() {
        UserAccount user = makeUser();
        Api client = anonymous();
        Response tokensResp = client.post(A + "/login/", m("username", user.getUsername(), "password", PASSWORD));
        String refresh = tokensResp.str("refresh");
        assertThat(client.post(A + "/logout/", m("refresh", refresh)).status()).isEqualTo(204);
        assertThat(client.post(A + "/token/refresh/", m("refresh", refresh)).status()).isEqualTo(401);
    }

    @Test
    void rotatedRefreshTokenIsSingleUse() {
        UserAccount user = makeUser();
        Api client = anonymous();
        String refresh = client.post(A + "/login/", m("username", user.getUsername(), "password", PASSWORD)).str("refresh");
        Response first = client.post(A + "/token/refresh/", m("refresh", refresh));
        assertThat(first.status()).isEqualTo(200);
        assertThat(first.str("refresh")).isNotBlank();
        assertThat(client.post(A + "/token/refresh/", m("refresh", refresh)).status()).isEqualTo(401);
        assertThat(client.post(A + "/token/refresh/", m("refresh", first.str("refresh"))).status()).isEqualTo(200);
    }

    @Test
    void userLookupReturnsNoIdentity() {
        Api api = api(makeUser());
        UserAccount target = makeUser(false, "Secret", "Person");
        Response body = api.get("/api/v1/budgeting/personal-budgets/users/lookup/", "email", target.getEmail());
        assertThat(body.get("found")).isEqualTo(true);
        assertThat(body.map()).doesNotContainKey("user");
        assertThat(String.valueOf(body.body())).doesNotContain("Secret").doesNotContain(target.getUsername());
    }

    @Test
    void healthHasNoSideEffects() {
        Response r = anonymous().get("/healthz/");
        assertThat(r.status()).isEqualTo(200);
        assertThat(r.map()).isEqualTo(java.util.Map.of("status", "ok"));
    }
}
