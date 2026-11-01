package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.PersonalBudgetNotification;
import com.financetracker.finance.domain.FinanceRepositories.PersonalBudgetNotificationRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaPersonalBudgetNotificationRepository extends PersonalBudgetNotificationRepository, Repository<PersonalBudgetNotification, String> {
}
