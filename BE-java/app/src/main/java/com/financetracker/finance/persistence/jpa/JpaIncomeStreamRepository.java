package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.IncomeStream;
import com.financetracker.finance.domain.FinanceRepositories.IncomeStreamRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaIncomeStreamRepository extends IncomeStreamRepository, Repository<IncomeStream, String> {
}
