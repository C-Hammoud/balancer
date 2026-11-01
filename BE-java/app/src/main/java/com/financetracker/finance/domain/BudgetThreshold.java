package com.financetracker.finance.domain;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Warn / critical utilization thresholds (BudgetThresholdFS). categoryId null = user's global default. */
@Entity
@Table(name = "fin_thresholds")
public class BudgetThreshold extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(length = 64)
    public String categoryId;

    @Column(nullable = false, precision = 5, scale = 1)
    public BigDecimal warnPct = new BigDecimal("80");

    @Column(nullable = false, precision = 5, scale = 1)
    public BigDecimal criticalPct = new BigDecimal("100");

    @Column(nullable = false)
    public boolean emailEnabled = true;
}
