package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.Savings;
import com.financetracker.finance.domain.FinanceRepositories.SavingsRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaSavingsRepository extends SavingsRepository, Repository<Savings, String> {
}
