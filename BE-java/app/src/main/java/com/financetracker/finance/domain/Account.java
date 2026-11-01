package com.financetracker.finance.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** Financial account used on transactions (IncomeSourceFS: bank, credit_card, wallet, other). */
@Entity
@Table(name = "fin_accounts")
public class Account extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(nullable = false, length = 120)
    public String name = "";

    @Column(nullable = false, length = 20)
    public String accountType = "bank";

    @Column(name = "sort_order", nullable = false)
    public int order;

    @Column(nullable = false)
    public boolean active = true;

    @Column(nullable = false)
    public boolean defaultForExpenses;
}
