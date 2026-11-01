package com.financetracker.access.security;

import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.MessageDigest;
import java.util.Base64;
import java.util.LinkedHashMap;
import java.util.Map;

import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;

import tools.jackson.core.JacksonException;
import tools.jackson.databind.json.JsonMapper;

/**
 * HS256 JWT encode/decode with PyJWT's checks and simplejwt's error messages. Only HS256 is
 * accepted (no "none", no algorithm switching).
 */
public final class JwtCodec {

    private static final JsonMapper JSON = JsonMapper.builder().build();
    private static final Base64.Encoder B64 = Base64.getUrlEncoder().withoutPadding();
    private static final Base64.Decoder B64D = Base64.getUrlDecoder();

    private final byte[] key;

    public JwtCodec(String signingKey) {
        this.key = signingKey.getBytes(StandardCharsets.UTF_8);
    }

    public String encode(Map<String, Object> payload) {
        Map<String, Object> header = new LinkedHashMap<>();
        header.put("alg", "HS256");
        header.put("typ", "JWT");
        String signingInput = B64.encodeToString(JSON.writeValueAsBytes(header)) + "."
                + B64.encodeToString(JSON.writeValueAsBytes(payload));
        return signingInput + "." + B64.encodeToString(sign(signingInput));
    }

    /**
     * Verify signature and registered claims. Errors use simplejwt's TokenBackend wording:
     * "Token is expired", "Token is invalid", "Invalid algorithm specified".
     */
    @SuppressWarnings("unchecked")
    public Map<String, Object> decode(String token, long nowEpochSeconds) throws TokenError {
        if (token == null) {
            throw new TokenError("Token is invalid");
        }
        String[] parts = token.split("\\.", -1);
        if (parts.length != 3) {
            throw new TokenError("Token is invalid");
        }
        Map<String, Object> header;
        Map<String, Object> payload;
        byte[] signature;
        try {
            header = JSON.readValue(B64D.decode(parts[0]), Map.class);
            payload = JSON.readValue(B64D.decode(parts[1]), Map.class);
            signature = B64D.decode(parts[2]);
        } catch (IllegalArgumentException | JacksonException e) {
            throw new TokenError("Token is invalid");
        }
        if (!"HS256".equals(header.get("alg"))) {
            throw new TokenError("Invalid algorithm specified");
        }
        byte[] expected = sign(parts[0] + "." + parts[1]);
        if (!MessageDigest.isEqual(expected, signature)) {
            throw new TokenError("Token is invalid");
        }
        Object exp = payload.get("exp");
        if (exp != null) {
            if (!(exp instanceof Integer || exp instanceof Long)) {
                throw new TokenError("Token is invalid");
            }
            if (((Number) exp).longValue() <= nowEpochSeconds) {
                throw new TokenError("Token is expired");
            }
        }
        Object iat = payload.get("iat");
        if (iat != null) {
            if (!(iat instanceof Number)) {
                throw new TokenError("Token is invalid");
            }
            if (((Number) iat).longValue() > nowEpochSeconds) {
                throw new TokenError("Token is invalid");
            }
        }
        Object nbf = payload.get("nbf");
        if (nbf != null && (!(nbf instanceof Number) || ((Number) nbf).longValue() > nowEpochSeconds)) {
            throw new TokenError("Token is invalid");
        }
        return payload;
    }

    private byte[] sign(String input) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key.length == 0 ? new byte[1] : key, "HmacSHA256"));
            return mac.doFinal(input.getBytes(StandardCharsets.US_ASCII));
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException(e);
        }
    }
}
