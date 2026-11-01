package com.financetracker.finance.domain;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Index;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/**
 * Monthly forecast (BudgetFS) for a subcategory (categoryId set) or a parent group
 * (groupId set, categoryId empty).
 */
@Entity
@Table(name = "fin_budgets", indexes = @Index(name = "ix_fin_budgets_user_period", columnList = "user_id, period_year, period_month"))
public class Budget extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(nullable = false, length = 64)
    public String categoryId = "";

    @Column(nullable = false, length = 64)
    public String groupId = "";

    @Column(name = "period_year", nullable = false)
    public int year;

    @Column(name = "period_month", nullable = false)
    public int month;

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal forecast = BigDecimal.ZERO;
}
