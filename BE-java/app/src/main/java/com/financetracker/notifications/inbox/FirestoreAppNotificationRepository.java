package com.financetracker.notifications.inbox;

import static com.financetracker.shared.datastore.FirestoreDocs.bool;
import static com.financetracker.shared.datastore.FirestoreDocs.instant;
import static com.financetracker.shared.datastore.FirestoreDocs.str;
import static com.financetracker.shared.datastore.FirestoreDocs.ts;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Repository;

import com.financetracker.shared.config.DataStoreType;
import com.financetracker.shared.datastore.ConditionalOnDataStore;
import com.financetracker.shared.datastore.FirestoreCrud;
import com.google.cloud.firestore.Firestore;

/** Same collection and fields as Django's NotificationFS ("app_notifications"). */
@Repository
@ConditionalOnDataStore(DataStoreType.FIRESTORE)
class FirestoreAppNotificationRepository extends FirestoreCrud<AppNotification> implements AppNotificationRepository {

    FirestoreAppNotificationRepository(Firestore db) {
        super(db, "app_notifications");
    }

    @Override
    protected Map<String, Object> toDoc(AppNotification n) {
        Map<String, Object> d = new HashMap<>();
        d.put("user_id", n.userId);
        d.put("created_at", ts(n.createdAt));
        d.put("kind", n.kind);
        d.put("title", n.title);
        d.put("body", n.body);
        d.put("link", n.link);
        d.put("related_id", n.relatedId);
        d.put("fingerprint", n.fingerprint);
        d.put("is_read", n.isRead);
        return d;
    }

    @Override
    protected AppNotification fromDoc(String id, Map<String, Object> d) {
        AppNotification n = new AppNotification();
        n.userId = str(d, "user_id");
        n.createdAt = instant(d, "created_at");
        n.kind = str(d, "kind");
        n.title = str(d, "title");
        n.body = str(d, "body");
        n.link = str(d, "link");
        n.relatedId = str(d, "related_id");
        n.fingerprint = str(d, "fingerprint");
        n.isRead = bool(d, "is_read", false);
        return n;
    }

    @Override
    public List<AppNotification> findByUserIdOrderByIdAsc(String userId) {
        return where("user_id", userId);
    }

    @Override
    public boolean existsByUserIdAndFingerprint(String userId, String fingerprint) {
        return exists("user_id", userId, "fingerprint", fingerprint);
    }
}
