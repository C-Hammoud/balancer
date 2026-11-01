package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.PersonalBudgetCategory;
import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetCategoryRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaPersonalBudgetCategoryRepository extends PersonalBudgetCategoryRepository, Repository<PersonalBudgetCategory, String> {
}
