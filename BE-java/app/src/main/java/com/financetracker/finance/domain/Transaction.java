package com.financetracker.finance.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Bank / card / wallet transaction (TransactionFS). Transfers are excluded from expense totals. */
@Entity
@Table(name = "fin_transactions", indexes = {
        @Index(name = "ix_fin_txn_user_month", columnList = "user_id, txn_month"),
        @Index(name = "ix_fin_txn_budget", columnList = "budget_id"),
        @Index(name = "ix_fin_txn_external", columnList = "user_id, external_id")})
public class Transaction extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(name = "txn_date")
    public LocalDate date;

    /** YYYY-MM */
    @Column(name = "txn_month", nullable = false, length = 7)
    public String month = "";

    @Column(nullable = false, length = 500)
    public String description = "";

    @Column(length = 64)
    public String categoryId;

    @Column(length = 20)
    public String classification;

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal amount = BigDecimal.ZERO;

    @Column(nullable = false, length = 20)
    public String direction = "expense";

    @Column(nullable = false, length = 3)
    public String currency = "USD";

    @Column(nullable = false, length = 4000)
    public String note = "";

    /** HH:MM */
    @Column(name = "txn_time", nullable = false, length = 8)
    public String time = "";

    @Column(nullable = false, length = 100)
    public String sourceAccount = "";

    @Column(nullable = false, length = 64)
    public String incomeSourceId = "";

    @Column(nullable = false, length = 64)
    public String commitmentId = "";

    @Column(nullable = false, length = 64)
    public String scheduleLineId = "";

    @Column(nullable = false, length = 255)
    public String externalId = "";

    @Column(nullable = false)
    public boolean includeInUtilization;

    @Column(nullable = false, length = 64)
    public String budgetId = "";

    @Column(nullable = false, length = 64)
    public String budgetCategoryId = "";

    public Instant createdAt;
    public Instant updatedAt;

    @Override
    public void beforeSave(Instant now) {
        if (createdAt == null) {
            createdAt = now;
        }
        updatedAt = now;
        if (description != null && description.length() > 500) {
            description = description.substring(0, 500);
        }
        if (time != null && time.length() > 8) {
            time = time.substring(0, 8);
        }
    }
}
