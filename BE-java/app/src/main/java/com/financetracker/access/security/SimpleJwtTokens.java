package com.financetracker.access.security;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.UUID;

import org.springframework.stereotype.Component;

import com.financetracker.access.domain.AccessRepositories.RefreshTokenRepository;
import com.financetracker.access.domain.RefreshTokenRecord;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.shared.config.AppProperties;

/**
 * djangorestframework-simplejwt 5.5 behaviour: refresh/access token pair with claims
 * token_type, exp, iat, jti, user_id (string), refresh rotation and blacklist.
 */
@Component
public class SimpleJwtTokens {

    public record Pair(String refresh, String access) {
    }

    private static final Set<String> NO_COPY_CLAIMS = Set.of("token_type", "exp", "jti");

    private final JwtCodec codec;
    private final Duration accessLifetime;
    private final Duration refreshLifetime;
    private final RefreshTokenRepository refreshTokens;
    private final Clock clock;

    public SimpleJwtTokens(AppProperties props, RefreshTokenRepository refreshTokens, Clock clock) {
        String signingKey = props.getJwt().getSigningKey();
        this.codec = new JwtCodec(signingKey == null || signingKey.isBlank() ? props.getSecretKey() : signingKey);
        this.accessLifetime = props.getJwt().getAccessTokenLifetime();
        this.refreshLifetime = props.getJwt().getRefreshTokenLifetime();
        this.refreshTokens = refreshTokens;
        this.clock = clock;
    }

    /** RefreshToken.for_user(user) + its access_token (api.utils.jwt_for_user). */
    public Pair forUser(UserAccount user) {
        long now = now();
        Map<String, Object> refresh = newPayload("refresh", now, refreshLifetime);
        refresh.put("user_id", user.userId());
        String refreshStr = codec.encode(refresh);
        outstand(refresh, refreshStr);
        return new Pair(refreshStr, codec.encode(accessFrom(refresh, now)));
    }

    /** RefreshToken(raw): signature, blacklist, exp, jti and type checks. */
    public Map<String, Object> validateRefresh(String raw) throws TokenError {
        Map<String, Object> payload = codec.decode(raw, now());
        Object jti = payload.get("jti");
        if (jti != null && refreshTokens.findById(String.valueOf(jti)).map(RefreshTokenRecord::isBlacklisted).orElse(false)) {
            throw new TokenError("Token is blacklisted");
        }
        verify(payload, "refresh");
        return payload;
    }

    /** AccessToken(raw). */
    public Map<String, Object> validateAccess(String raw) throws TokenError {
        Map<String, Object> payload = codec.decode(raw, now());
        verify(payload, "access");
        return payload;
    }

    /** TokenRefreshSerializer.validate with ROTATE_REFRESH_TOKENS and BLACKLIST_AFTER_ROTATION. */
    public Map<String, Object> refresh(Map<String, Object> refreshPayload, String raw) {
        long now = now();
        Map<String, Object> data = new LinkedHashMap<>();
        data.put("access", codec.encode(accessFrom(refreshPayload, now)));
        blacklist(refreshPayload, raw);
        Map<String, Object> rotated = new LinkedHashMap<>(refreshPayload);
        rotated.put("jti", newJti());
        rotated.put("exp", now + refreshLifetime.getSeconds());
        rotated.put("iat", now);
        String rotatedStr = codec.encode(rotated);
        outstand(rotated, rotatedStr);
        data.put("refresh", rotatedStr);
        return data;
    }

    /** BlacklistMixin.blacklist(): record the token (if unknown) and mark it revoked. */
    public void blacklist(Map<String, Object> payload, String raw) {
        String jti = String.valueOf(payload.get("jti"));
        RefreshTokenRecord record = refreshTokens.findById(jti).orElseGet(() -> new RefreshTokenRecord(
                jti, userId(payload), raw, Instant.now(clock), Instant.ofEpochSecond(((Number) payload.get("exp")).longValue())));
        if (!record.isBlacklisted()) {
            record.setBlacklistedAt(Instant.now(clock));
        }
        refreshTokens.save(record);
    }

    private void outstand(Map<String, Object> payload, String raw) {
        String jti = String.valueOf(payload.get("jti"));
        if (refreshTokens.findById(jti).isEmpty()) {
            refreshTokens.save(new RefreshTokenRecord(jti, userId(payload), raw, Instant.now(clock),
                    Instant.ofEpochSecond(((Number) payload.get("exp")).longValue())));
        }
    }

    private Map<String, Object> accessFrom(Map<String, Object> refresh, long now) {
        Map<String, Object> access = newPayload("access", now, accessLifetime);
        refresh.forEach((claim, value) -> {
            if (!NO_COPY_CLAIMS.contains(claim)) {
                access.put(claim, value);
            }
        });
        return access;
    }

    private Map<String, Object> newPayload(String type, long now, Duration lifetime) {
        Map<String, Object> p = new LinkedHashMap<>();
        p.put("token_type", type);
        p.put("exp", now + lifetime.getSeconds());
        p.put("iat", now);
        p.put("jti", newJti());
        return p;
    }

    private void verify(Map<String, Object> payload, String expectedType) throws TokenError {
        Object exp = payload.get("exp");
        if (exp == null) {
            throw new TokenError("Token has no 'exp' claim");
        }
        if (((Number) exp).longValue() <= now()) {
            throw new TokenError("Token 'exp' claim has expired");
        }
        if (!payload.containsKey("jti")) {
            throw new TokenError("Token has no id");
        }
        Object type = payload.get("token_type");
        if (type == null && !payload.containsKey("token_type")) {
            throw new TokenError("Token has no type");
        }
        if (!expectedType.equals(type)) {
            throw new TokenError("Token has wrong type");
        }
    }

    private static Long userId(Map<String, Object> payload) {
        Object v = payload.get("user_id");
        if (v == null) {
            return null;
        }
        try {
            return Long.valueOf(String.valueOf(v));
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private static String newJti() {
        return UUID.randomUUID().toString().replace("-", "");
    }

    private long now() {
        return Instant.now(clock).getEpochSecond();
    }
}
