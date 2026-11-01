package com.financetracker.finance.domain;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** In-app notice that a personal budget was shared with the recipient. */
@Entity
@Table(name = "fin_personal_budget_notifications")
public class PersonalBudgetNotification extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String recipientId = "";

    @Column(nullable = false, length = 64)
    public String budgetId = "";

    @Column(nullable = false, length = 64)
    public String sharedById = "";

    @Column(nullable = false, length = 20)
    public String role = PersonalBudgetMember.VIEWER;

    @Column(nullable = false, length = 200)
    public String title = "";

    @Column(nullable = false, length = 4000)
    public String message = "";

    public Instant readAt;
    public Instant createdAt;

    @Override
    public void beforeSave(Instant now) {
        if (createdAt == null) {
            createdAt = now;
        }
    }
}
