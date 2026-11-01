package com.financetracker.notifications.inbox;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Service;

import com.financetracker.notifications.api.InAppNotifications;
import com.financetracker.shared.web.Py;

/** In-app inbox (api/views/planning.py notification views + NotificationFS writes). */
@Service
class InboxService implements InAppNotifications {

    private final AppNotificationRepository notifications;

    InboxService(AppNotificationRepository notifications) {
        this.notifications = notifications;
    }

    @Override
    public boolean exists(String userId, String fingerprint) {
        return notifications.existsByUserIdAndFingerprint(userId, fingerprint);
    }

    @Override
    public String notify(String userId, String kind, String title, String body, String link, String relatedId,
            String fingerprint) {
        AppNotification n = new AppNotification();
        n.userId = userId;
        n.kind = kind;
        n.title = title;
        n.body = body;
        n.link = link;
        n.relatedId = relatedId == null ? "" : relatedId;
        n.fingerprint = fingerprint;
        return notifications.save(n).id;
    }

    List<Map<String, Object>> list(String userId, boolean unreadOnly) {
        return notifications.listByUser(userId, 100).stream()
                .filter(n -> !unreadOnly || !n.isRead)
                .map(InboxService::toJson)
                .toList();
    }

    long unreadCount(String userId) {
        return notifications.listByUser(userId, 500).stream().filter(n -> !n.isRead).count();
    }

    Optional<Map<String, Object>> markRead(String userId, String id) {
        return notifications.findById(id).filter(n -> userId.equals(n.userId)).map(n -> {
            if (!n.isRead) {
                n.isRead = true;
                notifications.save(n);
            }
            return toJson(n);
        });
    }

    int markAllRead(String userId) {
        int count = 0;
        for (AppNotification n : notifications.listByUser(userId, 500)) {
            if (!n.isRead) {
                n.isRead = true;
                notifications.save(n);
                count++;
            }
        }
        return count;
    }

    static Map<String, Object> toJson(AppNotification n) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", n.id);
        m.put("kind", n.kind);
        m.put("title", n.title);
        m.put("body", n.body);
        m.put("link", n.link);
        m.put("related_id", n.relatedId);
        m.put("is_read", n.isRead);
        m.put("created_at", Py.isoformat(n.createdAt));
        return m;
    }
}
