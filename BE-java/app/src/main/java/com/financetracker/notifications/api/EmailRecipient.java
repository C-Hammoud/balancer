package com.financetracker.notifications.api;

/** Who an email goes to, with the name fields the templates greet by. */
public record EmailRecipient(long userId, String email, String firstName, String lastName, String username) {

    /** emails._display_name: first name, else username, else the fallback. */
    public String displayName(String fallback) {
        String v = notEmpty(firstName) ? firstName : notEmpty(username) ? username : fallback;
        return v.strip();
    }

    /** emails._sharer_display: "First Last", else username. */
    public String sharerDisplay() {
        StringBuilder sb = new StringBuilder();
        if (notEmpty(firstName)) {
            sb.append(firstName);
        }
        if (notEmpty(lastName)) {
            if (sb.length() > 0) {
                sb.append(' ');
            }
            sb.append(lastName);
        }
        String full = sb.toString().strip();
        return !full.isEmpty() ? full : username == null ? "Someone" : username;
    }

    private static boolean notEmpty(String s) {
        return s != null && !s.isEmpty();
    }
}
