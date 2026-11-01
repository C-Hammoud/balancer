package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.PersonalBudget;
import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaPersonalBudgetRepository extends PersonalBudgetRepository, Repository<PersonalBudget, String> {
}
