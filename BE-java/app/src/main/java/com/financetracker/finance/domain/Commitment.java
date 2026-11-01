package com.financetracker.finance.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Loan / commitment (CommitmentFS). */
@Entity
@Table(name = "fin_commitments")
public class Commitment extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(nullable = false, length = 200)
    public String name = "";

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal amount = BigDecimal.ZERO;

    public LocalDate startDate;

    @Column(nullable = false)
    public int termMonths;

    @Column(nullable = false, length = 20)
    public String frequency = "monthly";

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal paymentAmount = BigDecimal.ZERO;

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal balloon = BigDecimal.ZERO;

    @Column(nullable = false, length = 3)
    public String currency = "USD";

    @Column(nullable = false)
    public boolean reminderEnabled = true;

    @Column(nullable = false)
    public int reminderDaysBefore = 3;

    public Instant createdAt;
    public Instant updatedAt;

    @Override
    public void beforeSave(Instant now) {
        if (createdAt == null) {
            createdAt = now;
        }
        updatedAt = now;
    }
}
