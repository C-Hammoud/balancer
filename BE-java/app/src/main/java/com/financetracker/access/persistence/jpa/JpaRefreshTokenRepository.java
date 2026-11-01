package com.financetracker.access.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.access.domain.AccessRepositories.RefreshTokenRepository;
import com.financetracker.access.domain.RefreshTokenRecord;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaRefreshTokenRepository extends RefreshTokenRepository, Repository<RefreshTokenRecord, String> {
}
