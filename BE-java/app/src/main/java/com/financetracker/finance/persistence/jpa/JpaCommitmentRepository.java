package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.Commitment;
import com.financetracker.finance.domain.FinanceRepositories.CommitmentRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaCommitmentRepository extends CommitmentRepository, Repository<Commitment, String> {
}
