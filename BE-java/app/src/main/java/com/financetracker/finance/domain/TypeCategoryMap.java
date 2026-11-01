package com.financetracker.finance.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Expense consumption type to subcategory (TypeCategoryMapFS). userId "" or null = global default. */
@Entity
@Table(name = "fin_type_category_maps")
public class TypeCategoryMap extends StoredEntity {

    @Column(length = 64)
    public String userId;

    @Column(nullable = false, length = 32)
    public String consumptionType = "other";

    @Column(nullable = false, length = 64)
    public String categoryId = "";
}
