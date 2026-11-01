package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.BudgetThreshold;
import com.financetracker.finance.domain.FinanceRepositories.BudgetThresholdRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaBudgetThresholdRepository extends BudgetThresholdRepository, Repository<BudgetThreshold, String> {
}
