package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.TypeCategoryMap;
import com.financetracker.finance.domain.FinanceRepositories.TypeCategoryMapRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaTypeCategoryMapRepository extends TypeCategoryMapRepository, Repository<TypeCategoryMap, String> {
}
