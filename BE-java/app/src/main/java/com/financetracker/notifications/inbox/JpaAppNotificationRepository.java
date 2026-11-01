package com.financetracker.notifications.inbox;

import org.springframework.data.repository.Repository;

/** JPA adapter: Spring Data implements the port (registered only when app.datastore=jpa). */
interface JpaAppNotificationRepository extends AppNotificationRepository, Repository<AppNotification, String> {
}
