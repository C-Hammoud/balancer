package com.financetracker.shared.security;

import java.util.Optional;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

import com.financetracker.shared.error.ApiException;

/** Access to the authenticated {@link AuthUser} (DRF {@code request.user}). */
public final class CurrentUser {

    private CurrentUser() {
    }

    public static Optional<AuthUser> get() {
        Authentication auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth != null && auth.getPrincipal() instanceof AuthUser user) {
            return Optional.of(user);
        }
        return Optional.empty();
    }

    /** The signed-in user, or 401 "Authentication credentials were not provided." */
    public static AuthUser require() {
        return get().orElseThrow(() -> ApiException.unauthorized("Authentication credentials were not provided."));
    }
}
