package com.financetracker.finance.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Snapshot of assets and liabilities (FinancialStandingFS). */
@Entity
@Table(name = "fin_financial_standings")
public class FinancialStanding extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String userId = "";

    public LocalDate snapshotDate;

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal totalAssets = BigDecimal.ZERO;
    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal currentAssets = BigDecimal.ZERO;
    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal fixedAssets = BigDecimal.ZERO;
    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal totalLiabilities = BigDecimal.ZERO;
    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal shortTermLiabilities = BigDecimal.ZERO;
    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal longTermLiabilities = BigDecimal.ZERO;

    @Column(nullable = false, length = 4000)
    public String notes = "";

    public Instant createdAt;

    @Override
    public void beforeSave(Instant now) {
        if (createdAt == null) {
            createdAt = now;
        }
    }
}
