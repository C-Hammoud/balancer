package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.PersonalBudgetInvite;
import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetInviteRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaPersonalBudgetInviteRepository extends PersonalBudgetInviteRepository, Repository<PersonalBudgetInvite, String> {
}
