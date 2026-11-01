package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.Transaction;
import com.financetracker.finance.domain.FinanceRepositories.TransactionRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaTransactionRepository extends TransactionRepository, Repository<Transaction, String> {
}
