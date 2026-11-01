package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.FinancialStanding;
import com.financetracker.finance.domain.FinanceRepositories.FinancialStandingRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaFinancialStandingRepository extends FinancialStandingRepository, Repository<FinancialStanding, String> {
}
