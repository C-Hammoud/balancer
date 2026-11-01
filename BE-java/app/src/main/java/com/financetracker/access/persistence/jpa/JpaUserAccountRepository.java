package com.financetracker.access.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.access.domain.AccessRepositories.UserAccountRepository;
import com.financetracker.access.domain.UserAccount;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaUserAccountRepository extends UserAccountRepository, Repository<UserAccount, Long> {
}
