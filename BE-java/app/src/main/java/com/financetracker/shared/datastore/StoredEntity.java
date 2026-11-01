package com.financetracker.shared.datastore;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Id;
import jakarta.persistence.MappedSuperclass;
import jakarta.persistence.PostLoad;
import jakarta.persistence.PostPersist;
import jakarta.persistence.Transient;

import org.springframework.data.domain.Persistable;

/**
 * Base for records with string ids (Firestore-style, assigned on creation). Fields are public:
 * these classes are plain data records ported from the Django/Firestore dataclasses.
 * {@link #beforeSave(Instant)} plays the role of the dataclass save() hooks (timestamps,
 * normalisation) and is called by both the JPA and the Firestore adapters.
 */
@MappedSuperclass
public abstract class StoredEntity implements Persistable<String> {

    @Id
    @Column(length = 64)
    public String id = Ids.newId();

    @Transient
    private boolean persisted;

    @Override
    public String getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return !persisted;
    }

    @PostLoad
    @PostPersist
    void markPersisted() {
        persisted = true;
    }

    /** Called by adapters that load records themselves (Firestore). */
    public void markLoaded() {
        persisted = true;
    }

    /** Hook run before every save. */
    public void beforeSave(Instant now) {
    }
}
