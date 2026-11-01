package com.financetracker.shared.security;

/**
 * The signed-in user, as put in the security context by the access module's JWT filter.
 * Modules use {@link #userId()} (the Django {@code str(user.pk)}) to scope their data.
 */
public record AuthUser(long id, String username, boolean staff) {

    public String userId() {
        return String.valueOf(id);
    }
}
