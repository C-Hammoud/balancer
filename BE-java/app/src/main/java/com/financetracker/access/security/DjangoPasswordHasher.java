package com.financetracker.access.security;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

import javax.crypto.SecretKeyFactory;
import javax.crypto.spec.PBEKeySpec;

import org.springframework.stereotype.Component;

import com.financetracker.shared.config.AppProperties;

/**
 * Django's PBKDF2 password hasher. Reads and writes the same "pbkdf2_sha256$iter$salt$hash"
 * strings, so existing passwords keep working and Django can still read hashes written here.
 */
@Component
public class DjangoPasswordHasher {

    private static final String ALGORITHM = "pbkdf2_sha256";
    private static final String SALT_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
    private static final SecureRandom RANDOM = new SecureRandom();

    private final int iterations;

    public DjangoPasswordHasher(AppProperties props) {
        this.iterations = props.getPasswordHashIterations();
    }

    public String encode(String raw) {
        StringBuilder salt = new StringBuilder(22);
        for (int i = 0; i < 22; i++) {
            salt.append(SALT_CHARS.charAt(RANDOM.nextInt(SALT_CHARS.length())));
        }
        return encode(raw, salt.toString(), iterations, "PBKDF2WithHmacSHA256", ALGORITHM);
    }

    /** Django check_password(): false for empty or unusable ("!...") hashes. */
    public boolean matches(String raw, String encoded) {
        if (raw == null || encoded == null || encoded.isEmpty() || encoded.startsWith("!")) {
            return false;
        }
        String[] parts = encoded.split("\\$", 4);
        if (parts.length != 4) {
            return false;
        }
        String jca = switch (parts[0]) {
            case "pbkdf2_sha256" -> "PBKDF2WithHmacSHA256";
            case "pbkdf2_sha1" -> "PBKDF2WithHmacSHA1";
            default -> null;
        };
        if (jca == null) {
            return false;
        }
        int iter;
        try {
            iter = Integer.parseInt(parts[1]);
        } catch (NumberFormatException e) {
            return false;
        }
        String candidate = encode(raw, parts[2], iter, jca, parts[0]);
        return MessageDigest.isEqual(candidate.getBytes(StandardCharsets.UTF_8), encoded.getBytes(StandardCharsets.UTF_8));
    }

    /** Django must_update(): older algorithm or a different iteration count. */
    public boolean mustUpdate(String encoded) {
        String[] parts = encoded == null ? new String[0] : encoded.split("\\$", 4);
        return parts.length != 4 || !ALGORITHM.equals(parts[0]) || !String.valueOf(iterations).equals(parts[1]);
    }

    private static String encode(String raw, String salt, int iter, String jca, String algorithm) {
        try {
            int keyLength = "PBKDF2WithHmacSHA1".equals(jca) ? 160 : 256;
            PBEKeySpec spec = new PBEKeySpec(raw.toCharArray(), salt.getBytes(StandardCharsets.UTF_8), iter, keyLength);
            byte[] hash = SecretKeyFactory.getInstance(jca).generateSecret(spec).getEncoded();
            return algorithm + "$" + iter + "$" + salt + "$" + Base64.getEncoder().encodeToString(hash);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("PBKDF2 unavailable", e);
        }
    }
}
