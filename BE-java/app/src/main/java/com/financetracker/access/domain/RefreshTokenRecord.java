package com.financetracker.access.domain;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/**
 * Issued refresh token (simplejwt OutstandingToken) and its revocation (BlacklistedToken),
 * merged into one record.
 */
@Entity
@Table(name = "access_refresh_tokens")
public class RefreshTokenRecord {

    @Id
    @Column(length = 255)
    private String jti;

    private Long userId;

    @Column(length = 2048)
    private String token;

    private Instant createdAt;

    @Column(nullable = false)
    private Instant expiresAt;

    private Instant blacklistedAt;

    protected RefreshTokenRecord() {
    }

    public RefreshTokenRecord(String jti, Long userId, String token, Instant createdAt, Instant expiresAt) {
        this.jti = jti;
        this.userId = userId;
        this.token = token;
        this.createdAt = createdAt;
        this.expiresAt = expiresAt;
    }

    public boolean isBlacklisted() {
        return blacklistedAt != null;
    }

    public String getJti() { return jti; }
    public Long getUserId() { return userId; }
    public String getToken() { return token; }
    public Instant getCreatedAt() { return createdAt; }
    public Instant getExpiresAt() { return expiresAt; }
    public Instant getBlacklistedAt() { return blacklistedAt; }
    public void setBlacklistedAt(Instant v) { this.blacklistedAt = v; }
}
