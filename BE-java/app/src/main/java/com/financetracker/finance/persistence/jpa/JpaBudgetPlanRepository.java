package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.BudgetPlan;
import com.financetracker.finance.domain.FinanceRepositories.BudgetPlanRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaBudgetPlanRepository extends BudgetPlanRepository, Repository<BudgetPlan, String> {
}
