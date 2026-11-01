package com.financetracker.finance.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Parent category (GroupFS). userId "" = shared default. */
@Entity
@Table(name = "fin_groups")
public class CategoryGroup extends StoredEntity {

    @Column(nullable = false, length = 120)
    public String name = "";

    @Column(name = "sort_order", nullable = false)
    public int order;

    @Column(nullable = false, length = 64)
    public String userId = "";
}
