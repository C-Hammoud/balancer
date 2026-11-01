package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.Category;
import com.financetracker.finance.domain.FinanceRepositories.CategoryRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaCategoryRepository extends CategoryRepository, Repository<Category, String> {
}
