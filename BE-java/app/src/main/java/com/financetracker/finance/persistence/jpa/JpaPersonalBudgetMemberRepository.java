package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.PersonalBudgetMember;
import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetMemberRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaPersonalBudgetMemberRepository extends PersonalBudgetMemberRepository, Repository<PersonalBudgetMember, String> {
}
