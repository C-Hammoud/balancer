package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.CategoryGroup;
import com.financetracker.finance.domain.FinanceRepositories.GroupRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaGroupRepository extends GroupRepository, Repository<CategoryGroup, String> {
}
