package com.financetracker.finance.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;
import jakarta.persistence.Transient;

import com.financetracker.shared.datastore.StoredEntity;

/** Subcategory (CategoryFS) under a group. userId "" = shared default. */
@Entity
@Table(name = "fin_categories")
public class Category extends StoredEntity {

    @Column(nullable = false, length = 120)
    public String name = "";

    @Column(nullable = false, length = 64)
    public String groupId = "";

    @Column(nullable = false)
    public boolean includeInReports = true;

    @Column(name = "sort_order", nullable = false)
    public int order;

    @Column(nullable = false, length = 64)
    public String userId = "";

    /** Filled by categories_and_groups_for_user; not stored. */
    @Transient
    public String groupName = "";
}
