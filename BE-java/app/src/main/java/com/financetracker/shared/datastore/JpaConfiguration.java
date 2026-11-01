package com.financetracker.shared.datastore;

import org.springframework.context.annotation.Configuration;
import org.springframework.data.jpa.repository.config.EnableJpaRepositories;

import com.financetracker.shared.config.DataStoreType;

/** Spring Data JPA repositories for every module (only when app.datastore=jpa). */
@Configuration(proxyBeanMethods = false)
@ConditionalOnDataStore(DataStoreType.JPA)
@EnableJpaRepositories(basePackages = "com.financetracker", repositoryBaseClass = StoringJpaRepository.class)
class JpaConfiguration {
}
