package com.financetracker.access.api;

/** Read-only view of a user for other modules (replaces direct User.objects lookups). */
public record UserSummary(
        long id,
        String username,
        String email,
        String firstName,
        String lastName,
        boolean staff,
        boolean active) {

    public String userId() {
        return String.valueOf(id);
    }
}
