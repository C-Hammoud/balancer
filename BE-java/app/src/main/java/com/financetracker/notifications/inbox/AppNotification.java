package com.financetracker.notifications.inbox;

import java.time.Instant;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

import com.financetracker.shared.datastore.StoredEntity;

/** General in-app notification that links to an app route (Django Notification / NotificationFS). */
@Entity
@Table(name = "ntf_notifications")
public class AppNotification extends StoredEntity {

    @Column(nullable = false, length = 64)
    public String userId = "";

    @Column(nullable = false, length = 40)
    public String kind = "";

    @Column(nullable = false, length = 200)
    public String title = "";

    @Column(nullable = false, length = 4000)
    public String body = "";

    @Column(nullable = false, length = 300)
    public String link = "";

    @Column(nullable = false, length = 64)
    public String relatedId = "";

    @Column(nullable = false, length = 255)
    public String fingerprint = "";

    @Column(nullable = false)
    public boolean isRead;

    public Instant createdAt;

    @Override
    public void beforeSave(Instant now) {
        if (createdAt == null) {
            createdAt = now;
        }
    }
}
