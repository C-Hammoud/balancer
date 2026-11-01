package com.financetracker.finance.persistence.jpa;

import org.springframework.data.repository.Repository;

import com.financetracker.finance.domain.MerchantLink;
import com.financetracker.finance.domain.FinanceRepositories.MerchantLinkRepository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaMerchantLinkRepository extends MerchantLinkRepository, Repository<MerchantLink, String> {
}
