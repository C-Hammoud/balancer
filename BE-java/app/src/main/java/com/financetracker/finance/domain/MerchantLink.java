package com.financetracker.finance.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Keyword to subcategory mapping for automatic classification (MerchantCategoryLinkFS). */
@Entity
@Table(name = "fin_merchant_links")
public class MerchantLink extends StoredEntity {

    @Column(nullable = false, length = 120)
    public String keyword = "";

    @Column(nullable = false, length = 64)
    public String categoryId = "";

    /** null = global link. */
    @Column(length = 64)
    public String userId;
}
