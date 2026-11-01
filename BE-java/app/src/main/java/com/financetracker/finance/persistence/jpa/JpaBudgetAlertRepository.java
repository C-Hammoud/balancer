package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.BudgetAlert;
import com.financetracker.finance.domain.FinanceRepositories.BudgetAlertRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaBudgetAlertRepository extends BudgetAlertRepository, Repository<BudgetAlert, String> {
}
