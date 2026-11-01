package com.financetracker.finance.application;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

import com.financetracker.access.api.EmailVerified;

/** Reactions to events from other modules. */
@Component
class FinanceEventListeners {

    private static final Logger log = LoggerFactory.getLogger(FinanceEventListeners.class);

    private final SharingService sharing;

    FinanceEventListeners(SharingService sharing) {
        this.sharing = sharing;
    }

    /** Pending shared-budget invites for the address become memberships once it is verified. */
    @EventListener
    void onEmailVerified(EmailVerified event) {
        try {
            sharing.acceptPendingInvites(event.userId(), event.email());
        } catch (RuntimeException e) {
            log.warn("Failed to apply pending budget invites for user {}: {}", event.userId(), e.getMessage());
        }
    }
}
