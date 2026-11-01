package com.financetracker.access.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.access.domain.AccessRepositories.UserProfileRepository;
import com.financetracker.access.domain.UserProfile;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaUserProfileRepository extends UserProfileRepository, Repository<UserProfile, Long> {
}
