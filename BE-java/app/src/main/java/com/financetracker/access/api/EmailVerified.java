package com.financetracker.access.api;

/**
 * Published (synchronously) after a user confirms their email. The finance module applies pending
 * shared-budget invites for that address, as api/email_verification.py did.
 */
public record EmailVerified(String userId, String email) {
}
