package com.financetracker.finance.domain;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** User-owned plan such as "Vacation" (PersonalBudgetFS); can be shared with viewers/editors. */
@Entity
@Table(name = "fin_personal_budgets")
public class PersonalBudget extends StoredEntity {

    public static final String DRAFT = "draft";
    public static final String ACTIVE = "active";
    public static final String COMPLETED = "completed";
    public static final String ARCHIVED = "archived";
    public static final java.util.List<String> STATUSES = java.util.List.of(DRAFT, ACTIVE, COMPLETED, ARCHIVED);

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(nullable = false, length = 120)
    public String name = "";

    @Column(nullable = false, length = 4000)
    public String description = "";

    @Column(nullable = false, length = 3)
    public String currency = "USD";

    public LocalDate startDate;
    public LocalDate endDate;

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal totalAmount = BigDecimal.ZERO;

    @Column(nullable = false, length = 20)
    public String status = DRAFT;

    @Column(nullable = false, length = 80)
    public String projectTag = "";

    @Column(nullable = false, length = 4000)
    public String notes = "";

    @Column(nullable = false)
    public boolean isDefault;

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
