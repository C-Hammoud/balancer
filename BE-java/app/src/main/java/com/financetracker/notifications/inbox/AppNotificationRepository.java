package com.financetracker.notifications.inbox;

import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

/** Port for the inbox (Spring Data naming; JPA and Firestore adapters). */
public interface AppNotificationRepository {

    Optional<AppNotification> findById(String id);

    List<AppNotification> findByUserIdOrderByIdAsc(String userId);

    boolean existsByUserIdAndFingerprint(String userId, String fingerprint);

    AppNotification save(AppNotification notification);

    /** Newest first. */
    default List<AppNotification> listByUser(String userId, int limit) {
        List<AppNotification> rows = new ArrayList<>(findByUserIdOrderByIdAsc(userId));
        rows.sort(Comparator.comparing((AppNotification n) -> n.createdAt,
                Comparator.nullsFirst(Comparator.<Instant>naturalOrder())).reversed());
        return rows.size() > limit ? new ArrayList<>(rows.subList(0, limit)) : rows;
    }
}
