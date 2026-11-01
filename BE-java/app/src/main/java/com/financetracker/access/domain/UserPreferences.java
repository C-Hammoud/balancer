package com.financetracker.access.domain;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

/** Port of budgeting UserPreferences / UserPreferencesFS (document id = user id). */
@Entity
@Table(name = "access_user_preferences")
public class UserPreferences {

    @Id
    @Column(length = 64)
    private String userId;

    @Column(nullable = false, length = 64)
    private String timezone = "";

    @Column(nullable = false, length = 8)
    private String country = "";

    @Column(nullable = false, length = 3)
    private String defaultCurrency = "USD";

    private Instant updatedAt;

    protected UserPreferences() {
    }

    public UserPreferences(String userId) {
        this.userId = userId;
    }

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }
    public String getTimezone() { return timezone; }
    public void setTimezone(String v) { this.timezone = v == null ? "" : v; }
    public String getCountry() { return country; }
    public void setCountry(String v) { this.country = v == null ? "" : v; }
    public String getDefaultCurrency() { return defaultCurrency; }
    public void setDefaultCurrency(String v) { this.defaultCurrency = v == null ? "USD" : v; }
    public Instant getUpdatedAt() { return updatedAt; }
    public void setUpdatedAt(Instant v) { this.updatedAt = v; }
}
