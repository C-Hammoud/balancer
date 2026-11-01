package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.Account;
import com.financetracker.finance.domain.FinanceRepositories.AccountRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaAccountRepository extends AccountRepository, Repository<Account, String> {
}
