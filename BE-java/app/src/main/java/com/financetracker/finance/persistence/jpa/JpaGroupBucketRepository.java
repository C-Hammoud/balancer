package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.GroupBucket;
import com.financetracker.finance.domain.FinanceRepositories.GroupBucketRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaGroupBucketRepository extends GroupBucketRepository, Repository<GroupBucket, String> {
}
