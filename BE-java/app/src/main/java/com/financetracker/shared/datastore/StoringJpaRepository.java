package com.financetracker.shared.datastore;

import java.time.Instant;

import jakarta.persistence.EntityManager;

import org.springframework.data.jpa.repository.support.JpaEntityInformation;
import org.springframework.data.jpa.repository.support.SimpleJpaRepository;
import org.springframework.transaction.annotation.Transactional;

/** JPA repository base: runs {@link StoredEntity#beforeSave(Instant)} on the caller's object before saving. */
public class StoringJpaRepository<T, ID> extends SimpleJpaRepository<T, ID> {

    public StoringJpaRepository(JpaEntityInformation<T, ?> entityInformation, EntityManager entityManager) {
        super(entityInformation, entityManager);
    }

    @Override
    @Transactional
    public <S extends T> S save(S entity) {
        if (entity instanceof StoredEntity stored) {
            stored.beforeSave(Instant.now());
        }
        return super.save(entity);
    }
}
