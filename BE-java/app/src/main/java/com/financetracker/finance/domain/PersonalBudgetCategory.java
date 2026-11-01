package com.financetracker.finance.domain;

import java.math.BigDecimal;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Category line within a personal budget; parentId links sub-lines to a group line. */
@Entity
@Table(name = "fin_personal_budget_categories")
public class PersonalBudgetCategory extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String budgetId = "";

    @Column(nullable = false, length = 120)
    public String name = "";

    @Column(nullable = false, precision = 14, scale = 2)
    public BigDecimal allocatedAmount = BigDecimal.ZERO;

    @Column(name = "sort_order", nullable = false)
    public int order;

    @Column(nullable = false, length = 4000)
    public String notes = "";

    @Column(nullable = false, length = 64)
    public String groupId = "";

    @Column(nullable = false, length = 64)
    public String categoryId = "";

    @Column(nullable = false, length = 64)
    public String parentId = "";
}
