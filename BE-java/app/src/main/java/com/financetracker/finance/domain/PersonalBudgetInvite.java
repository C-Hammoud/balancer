package com.financetracker.finance.domain;

import java.time.Instant;
import java.util.Locale;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Pending share for an email address that has no account yet. */
@Entity
@Table(name = "fin_personal_budget_invites")
public class PersonalBudgetInvite extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String budgetId = "";

    @Column(nullable = false, length = 254)
    public String email = "";

    @Column(nullable = false, length = 20)
    public String role = PersonalBudgetMember.VIEWER;

    @Column(nullable = false, length = 64)
    public String invitedById = "";

    public Instant createdAt;
    public Instant updatedAt;

    @Override
    public void beforeSave(Instant now) {
        if (createdAt == null) {
            createdAt = now;
        }
        updatedAt = now;
        email = email == null ? "" : email.toLowerCase(Locale.ROOT);
    }
}
