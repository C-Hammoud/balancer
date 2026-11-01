package com.financetracker.access.security;

/** simplejwt TokenError: the message is what the API returns in "detail". */
public class TokenError extends Exception {

    public TokenError(String message) {
        super(message);
    }
}
