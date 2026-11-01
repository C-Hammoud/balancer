package com.financetracker.access.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.access.domain.AccessRepositories.UserPreferencesRepository;
import com.financetracker.access.domain.UserPreferences;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaUserPreferencesRepository extends UserPreferencesRepository, Repository<UserPreferences, String> {
}
