package com.financetracker.access.security;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.LinkedHashMap;
import java.util.Map;

import org.junit.jupiter.api.Test;

import com.financetracker.access.domain.UserAccount;
import com.financetracker.shared.config.AppProperties;
import com.financetracker.shared.web.Py;

/**
 * Expected values were produced by Django 5.2.4 / PyJWT 2.13 from BE/venv with the same inputs
 * (script: PBKDF2PasswordHasher.encode, PasswordResetTokenGenerator.make_token, jwt.encode).
 */
class DjangoCompatibilityTest {

    static final String SECRET = "test-secret-key-for-compat-0123456789abcdef";
    static final String HASH_1000 = "pbkdf2_sha256$1000$abcdefghijklmnopqrstuv$L7fl4f3dd92YfDV94Lum80c7Tm7DdruC5VCeEwT5vjA=";
    static final String HASH_DEFAULT = "pbkdf2_sha256$1000000$abcdefghijklmnopqrstuv$8cw8DwpqhURHFjrJjH25mvsoyttq1LVcZiN0ayC65IU=";
    static final String PYJWT_ACCESS = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            + "eyJ0b2tlbl90eXBlIjoiYWNjZXNzIiwiZXhwIjo0MTAyNDQ0ODAwLCJpYXQiOjE3NjAwMDAwMDAsImp0aSI6IjAxMjM0NTY3ODlhYmNkZWYwMTIzNDU2Nzg5YWJjZGVmIiwidXNlcl9pZCI6IjQyIn0."
            + "6lg3-kToeygOx9PuVMwaKIGNirlVPf_yprBZOnzgUc4";

    private static DjangoPasswordHasher hasher(int iterations) {
        AppProperties props = new AppProperties();
        props.setPasswordHashIterations(iterations);
        return new DjangoPasswordHasher(props);
    }

    @Test
    void verifiesDjangoPasswordHashes() {
        DjangoPasswordHasher hasher = hasher(1000);
        assertThat(hasher.matches("S3cure-pass!", HASH_1000)).isTrue();
        assertThat(hasher.matches("S3cure-pass!", HASH_DEFAULT)).isTrue();
        assertThat(hasher.matches("wrong", HASH_1000)).isFalse();
        assertThat(hasher.matches("S3cure-pass!", "")).isFalse();
        assertThat(hasher.matches("S3cure-pass!", "!unusable")).isFalse();
    }

    @Test
    void newHashesAreDjangoFormatAndFlagOldIterationCounts() {
        DjangoPasswordHasher hasher = hasher(1000);
        String encoded = hasher.encode("another-Pass1");
        assertThat(encoded).matches("pbkdf2_sha256\\$1000\\$[A-Za-z0-9]{22}\\$[A-Za-z0-9+/=]{44}");
        assertThat(hasher.matches("another-Pass1", encoded)).isTrue();
        assertThat(hasher.mustUpdate(encoded)).isFalse();
        assertThat(hasher.mustUpdate(HASH_DEFAULT)).isTrue();
    }

    private static UserAccount user(Instant lastLogin) {
        UserAccount u = new UserAccount();
        u.setId(42L);
        u.setPassword(HASH_1000);
        u.setLastLogin(lastLogin);
        u.setEmail("Someone@Example.com");
        return u;
    }

    @Test
    void passwordResetAndVerificationTokensMatchDjango() {
        Clock clock = Clock.fixed(Instant.parse("2026-10-19T12:00:00Z"), ZoneOffset.UTC);
        Instant lastLogin = Instant.parse("2026-10-18T09:30:15.123456Z");
        DjangoTokenGenerator reset = new DjangoTokenGenerator(DjangoTokenGenerator.PASSWORD_RESET_SALT, SECRET,
                Duration.ofDays(3), clock);
        DjangoTokenGenerator verify = new DjangoTokenGenerator(DjangoTokenGenerator.EMAIL_VERIFICATION_SALT, SECRET,
                Duration.ofDays(3), clock);

        assertThat(reset.makeToken(user(lastLogin))).isEqualTo("dgp2o0-70fa570ab2ac5c655464b8ffe0f61c5a");
        assertThat(verify.makeToken(user(lastLogin))).isEqualTo("dgp2o0-4c35a68299ed0b66154ae827ea89cae7");
        assertThat(reset.makeToken(user(null))).isEqualTo("dgp2o0-c2299b3b8bb301397f7a6fd9351beae6");

        assertThat(reset.checkToken(user(lastLogin), "dgp2o0-70fa570ab2ac5c655464b8ffe0f61c5a")).isTrue();
        assertThat(verify.checkToken(user(lastLogin), "dgp2o0-70fa570ab2ac5c655464b8ffe0f61c5a")).isFalse();
        UserAccount changed = user(lastLogin);
        changed.setPassword("pbkdf2_sha256$1000$other$hash");
        assertThat(reset.checkToken(changed, "dgp2o0-70fa570ab2ac5c655464b8ffe0f61c5a")).isFalse();

        Clock fourDaysLater = Clock.fixed(Instant.parse("2026-10-23T12:00:01Z"), ZoneOffset.UTC);
        DjangoTokenGenerator late = new DjangoTokenGenerator(DjangoTokenGenerator.PASSWORD_RESET_SALT, SECRET,
                Duration.ofDays(3), fourDaysLater);
        assertThat(late.checkToken(user(lastLogin), "dgp2o0-70fa570ab2ac5c655464b8ffe0f61c5a")).isFalse();
    }

    @Test
    void jwtIsByteIdenticalToPyJwtAndVerifiesBothWays() throws TokenError {
        JwtCodec codec = new JwtCodec(SECRET);
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("token_type", "access");
        payload.put("exp", 4102444800L);
        payload.put("iat", 1760000000L);
        payload.put("jti", "0123456789abcdef0123456789abcdef");
        payload.put("user_id", "42");

        assertThat(codec.encode(payload)).isEqualTo(PYJWT_ACCESS);
        Map<String, Object> decoded = codec.decode(PYJWT_ACCESS, 1760000100L);
        assertThat(decoded).containsEntry("user_id", "42").containsEntry("token_type", "access");

        assertThatThrownBy(() -> new JwtCodec("another-secret").decode(PYJWT_ACCESS, 1760000100L))
                .isInstanceOf(TokenError.class).hasMessage("Token is invalid");
        assertThatThrownBy(() -> codec.decode(PYJWT_ACCESS, 4102444800L))
                .isInstanceOf(TokenError.class).hasMessage("Token is expired");
    }

    @Test
    void uidEncodingMatchesDjango() {
        assertThat(Py.urlsafeB64Encode("42")).isEqualTo("NDI");
        assertThat(Py.urlsafeB64Decode("NDI")).isEqualTo("42");
    }
}
