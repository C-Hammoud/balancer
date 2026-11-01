package com.financetracker.access.security;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.zip.GZIPInputStream;

import org.springframework.stereotype.Component;

/**
 * Django AUTH_PASSWORD_VALIDATORS as they apply in this API. The serializers call
 * validate_password(value) without a user, so UserAttributeSimilarityValidator never runs;
 * the remaining three run in settings order with Django's messages.
 */
@Component
public class PasswordPolicy {

    private static final int MIN_LENGTH = 8;
    private volatile Set<String> common;

    public List<String> validate(String password) {
        List<String> errors = new ArrayList<>();
        if (password.codePointCount(0, password.length()) < MIN_LENGTH) {
            errors.add("This password is too short. It must contain at least " + MIN_LENGTH + " characters.");
        }
        if (commonPasswords().contains(password.toLowerCase(Locale.ROOT).strip())) {
            errors.add("This password is too common.");
        }
        if (!password.isEmpty() && password.chars().allMatch(Character::isDigit)) {
            errors.add("This password is entirely numeric.");
        }
        return errors;
    }

    private Set<String> commonPasswords() {
        Set<String> c = common;
        if (c == null) {
            synchronized (this) {
                if (common == null) {
                    common = load();
                }
                c = common;
            }
        }
        return c;
    }

    private static Set<String> load() {
        Set<String> set = new HashSet<>();
        try (InputStream raw = PasswordPolicy.class.getResourceAsStream("/access/common-passwords.txt.gz")) {
            if (raw == null) {
                throw new IllegalStateException("common-passwords.txt.gz missing from resources");
            }
            try (BufferedReader r = new BufferedReader(
                    new InputStreamReader(new GZIPInputStream(raw), StandardCharsets.UTF_8))) {
                String line;
                while ((line = r.readLine()) != null) {
                    set.add(line.strip());
                }
            }
        } catch (IOException e) {
            throw new IllegalStateException("Could not read common passwords", e);
        }
        return set;
    }
}
