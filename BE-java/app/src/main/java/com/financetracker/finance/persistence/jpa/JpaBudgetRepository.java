package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.Budget;
import com.financetracker.finance.domain.FinanceRepositories.BudgetRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaBudgetRepository extends BudgetRepository, Repository<Budget, String> {
}
