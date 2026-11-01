package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.ScheduleLine;
import com.financetracker.finance.domain.FinanceRepositories.ScheduleLineRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaScheduleLineRepository extends ScheduleLineRepository, Repository<ScheduleLine, String> {
}
