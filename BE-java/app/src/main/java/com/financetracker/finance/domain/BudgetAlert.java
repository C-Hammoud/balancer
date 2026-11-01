package com.financetracker.finance.domain;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Utilization or commitment-due alert with its lifecycle (BudgetAlertFS). */
@Entity
@Table(name = "fin_alerts", indexes = @Index(name = "ix_fin_alerts_user", columnList = "user_id"))
public class BudgetAlert extends StoredEntity {

    public static final String RESOLUTION_USER = "user";
    public static final String RESOLUTION_AUTO = "auto";

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(name = "period_year", nullable = false)
    public int year;

    @Column(name = "period_month", nullable = false)
    public int month;

    @Column(nullable = false, length = 120)
    public String categoryId = "";

    @Column(nullable = false, length = 20)
    public String severity = "WARN";

    @Column(nullable = false, length = 200)
    public String title = "";

    @Column(nullable = false, length = 4000)
    public String description = "";

    /** utilization | commitment_due */
    @Column(nullable = false, length = 32)
    public String alertType = "utilization";

    @Column(precision = 8, scale = 2)
    public BigDecimal utilizationPct;

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal actual = BigDecimal.ZERO;

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal forecast = BigDecimal.ZERO;

    @Column(nullable = false, length = 64)
    public String commitmentId = "";

    @Column(nullable = false, length = 64)
    public String scheduleLineId = "";

    @Column(nullable = false, length = 32)
    public String dueDate = "";

    @Column(nullable = false, length = 200)
    public String commitmentName = "";

    @Column(nullable = false)
    public boolean isResolved;

    /** "user" = dismissed by the user; "auto" = condition cleared on re-evaluation. */
    @Column(nullable = false, length = 16)
    public String resolution = "";

    public Instant resolvedAt;
    public Instant snoozedUntil;

    @Column(nullable = false)
    public boolean emailSent;

    @Column(nullable = false, length = 255)
    public String fingerprint = "";

    public Instant createdAt;
    public Instant updatedAt;

    @Override
    public void beforeSave(Instant now) {
        if (createdAt == null) {
            createdAt = now;
        }
        updatedAt = now;
    }

    /** alert_state.alert_is_snoozed */
    public boolean isSnoozed(Instant now) {
        return snoozedUntil != null && !isResolved && snoozedUntil.isAfter(now);
    }

    /** alert_state.alert_state: open | snoozed | resolved */
    public String state(Instant now) {
        if (isResolved) {
            return "resolved";
        }
        return isSnoozed(now) ? "snoozed" : "open";
    }

    public static String fingerprint(String userId, int year, int month, String categoryId, String severity) {
        return userId + "|" + year + "|" + month + "|" + (categoryId == null || categoryId.isEmpty() ? "_" : categoryId)
                + "|" + severity;
    }
}
