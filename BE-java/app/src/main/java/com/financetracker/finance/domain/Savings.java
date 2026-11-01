package com.financetracker.finance.domain;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Monthly savings target / actual (SavingsFS). */
@Entity
@Table(name = "fin_savings")
public class Savings extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(name = "period_year", nullable = false)
    public int year;

    @Column(name = "period_month", nullable = false)
    public int month;

    /** null = derived from transactions. */
    @Column(precision = 14, scale = 2)
    public BigDecimal actual;

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal target = BigDecimal.ZERO;

    @Column(nullable = false, length = 20)
    public String goalStatus = "pending";
}
