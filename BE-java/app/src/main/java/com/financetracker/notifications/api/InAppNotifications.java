package com.financetracker.notifications.api;

/** The in-app inbox shown by the bell icon (GET /api/v1/notifications/). */
public interface InAppNotifications {

    /** Whether a notification with this fingerprint was already sent to the user. */
    boolean exists(String userId, String fingerprint);

    /** Stores a notification and returns its id. */
    String notify(String userId, String kind, String title, String body, String link, String relatedId, String fingerprint);
}
