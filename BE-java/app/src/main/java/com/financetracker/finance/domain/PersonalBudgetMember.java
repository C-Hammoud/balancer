package com.financetracker.finance.domain;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Access to a shared personal budget (viewer / editor). */
@Entity
@Table(name = "fin_personal_budget_members")
public class PersonalBudgetMember extends StoredEntity {

    public static final String VIEWER = "viewer";
    public static final String EDITOR = "editor";
    public static final String OWNER = "owner";
    public static final java.util.List<String> ROLES = java.util.List.of(VIEWER, EDITOR);

    @Column(nullable = false, length = 64)
    public String budgetId = "";

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(nullable = false, length = 20)
    public String role = VIEWER;

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
