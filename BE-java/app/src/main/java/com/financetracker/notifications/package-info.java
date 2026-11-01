/**
 * Notification management: branded transactional email (SMTP or console), the in-app notification
 * inboxes and delivery of reminders. Depends only on {@code shared}; other modules call
 * {@code notifications.api}.
 */
@ApplicationModule(displayName = "Notification management")
package com.financetracker.notifications;

import org.springframework.modulith.ApplicationModule;
