package com.financetracker.access.security;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.time.Clock;
import java.time.Duration;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;
import java.util.HexFormat;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import com.financetracker.access.domain.UserAccount;

/**
 * Port of django.contrib.auth.tokens.PasswordResetTokenGenerator. Tokens are "ts_b36-hash"
 * where hash = salted_hmac(key_salt, pk + password + last_login + ts + email)[::2], so links
 * emailed by Django stay valid here and become invalid once the password changes.
 */
public final class DjangoTokenGenerator {

    public static final String PASSWORD_RESET_SALT = "django.contrib.auth.tokens.PasswordResetTokenGenerator";
    public static final String EMAIL_VERIFICATION_SALT = "api.tokens.EmailVerificationTokenGenerator";

    private static final LocalDateTime EPOCH_2001 = LocalDateTime.of(2001, 1, 1, 0, 0);
    private static final DateTimeFormatter LOGIN_TS = DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm:ss");

    private final String keySalt;
    private final String secret;
    private final Duration timeout;
    private final Clock clock;

    public DjangoTokenGenerator(String keySalt, String secret, Duration timeout, Clock clock) {
        this.keySalt = keySalt;
        this.secret = secret;
        this.timeout = timeout;
        this.clock = clock;
    }

    public String makeToken(UserAccount user) {
        return makeTokenWithTimestamp(user, numSeconds(LocalDateTime.now(clock)));
    }

    public boolean checkToken(UserAccount user, String token) {
        if (user == null || token == null || token.isEmpty()) {
            return false;
        }
        String[] parts = token.split("-", -1);
        if (parts.length != 2) {
            return false;
        }
        long ts;
        try {
            ts = Long.parseLong(parts[0], 36);
        } catch (NumberFormatException e) {
            return false;
        }
        if (ts < 0 || parts[0].isEmpty() || !parts[0].equals(parts[0].toLowerCase())) {
            return false;
        }
        String expected = makeTokenWithTimestamp(user, ts);
        if (!MessageDigest.isEqual(expected.getBytes(StandardCharsets.UTF_8), token.getBytes(StandardCharsets.UTF_8))) {
            return false;
        }
        return numSeconds(LocalDateTime.now(clock)) - ts <= timeout.getSeconds();
    }

    private String makeTokenWithTimestamp(UserAccount user, long timestamp) {
        String hex = saltedHmac(hashValue(user, timestamp));
        StringBuilder every2nd = new StringBuilder(hex.length() / 2);
        for (int i = 0; i < hex.length(); i += 2) {
            every2nd.append(hex.charAt(i));
        }
        return Long.toString(timestamp, 36) + "-" + every2nd;
    }

    private static String hashValue(UserAccount user, long timestamp) {
        String loginTimestamp = user.getLastLogin() == null ? ""
                : LOGIN_TS.format(user.getLastLogin().atOffset(ZoneOffset.UTC).toLocalDateTime());
        return user.getId() + user.getPassword() + loginTimestamp + timestamp + (user.getEmail() == null ? "" : user.getEmail());
    }

    /** django.utils.crypto.salted_hmac(key_salt, value, secret, algorithm="sha256").hexdigest() */
    private String saltedHmac(String value) {
        try {
            byte[] key = MessageDigest.getInstance("SHA-256").digest((keySalt + secret).getBytes(StandardCharsets.UTF_8));
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return HexFormat.of().formatHex(mac.doFinal(value.getBytes(StandardCharsets.UTF_8)));
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(e);
        }
    }

    private static long numSeconds(LocalDateTime dt) {
        return Duration.between(EPOCH_2001, dt).getSeconds();
    }
}
