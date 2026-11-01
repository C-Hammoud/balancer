package com.financetracker.finance.domain;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** The user's needs / wants / savings classification of a category group. */
@Entity
@Table(name = "fin_group_buckets")
public class GroupBucket extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(nullable = false, length = 64)
    public String groupId = "";

    @Column(nullable = false, length = 16)
    public String bucket = "wants";

    public Instant createdAt;

    @Override
    public void beforeSave(Instant now) {
        if (createdAt == null) {
            createdAt = now;
        }
    }
}
