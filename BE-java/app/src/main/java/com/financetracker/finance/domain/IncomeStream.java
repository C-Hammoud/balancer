package com.financetracker.finance.domain;

import java.math.BigDecimal;
import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Expected recurring income (salary, rent received...). */
@Entity
@Table(name = "fin_income_streams")
public class IncomeStream extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(nullable = false, length = 120)
    public String name = "";

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal amount = BigDecimal.ZERO;

    @Column(nullable = false, length = 3)
    public String currency = "USD";

    /** monthly | biweekly | weekly | yearly */
    @Column(nullable = false, length = 16)
    public String frequency = "monthly";

    @Column(nullable = false, length = 64)
    public String accountId = "";

    @Column(nullable = false)
    public boolean active = true;

    public Instant createdAt;

    @Override
    public void beforeSave(Instant now) {
        if (createdAt == null) {
            createdAt = now;
        }
    }
}
