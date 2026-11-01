package com.financetracker.shared.web;

import java.net.IDN;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Port of django.core.validators.EmailValidator (Django 5.2). */
public final class EmailValidator {

    private static final Pattern USER = Pattern.compile(
            "(^[-!#$%&'*+/=?^_`{}|~0-9A-Z]+(\\.[-!#$%&'*+/=?^_`{}|~0-9A-Z]+)*\\z"
                    + "|^\"([\\x01-\\x08\\x0b\\x0c\\x0e-\\x1f!#-\\[\\]-\\x7f]|\\\\[\\x01-\\x09\\x0b\\x0c\\x0e-\\x7f])*\"\\z)",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern DOMAIN = Pattern.compile(
            "((?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\\.)+)(?:[A-Z0-9-]{2,63}(?<!-))\\z",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern LITERAL = Pattern.compile("\\[([A-F0-9:.]+)\\]\\z", Pattern.CASE_INSENSITIVE);

    private EmailValidator() {
    }

    public static boolean isValid(String value) {
        if (value == null || value.isEmpty() || !value.contains("@") || value.length() > 320) {
            return false;
        }
        int at = value.lastIndexOf('@');
        String user = value.substring(0, at);
        String domain = value.substring(at + 1);
        if (!USER.matcher(user).lookingAt()) {
            return false;
        }
        if ("localhost".equals(domain)) {
            return true;
        }
        if (validDomain(domain)) {
            return true;
        }
        try {
            String ascii = IDN.toASCII(domain);
            return !ascii.equals(domain) && validDomain(ascii);
        } catch (IllegalArgumentException e) {
            return false;
        }
    }

    private static boolean validDomain(String domain) {
        if (DOMAIN.matcher(domain).lookingAt()) {
            return true;
        }
        Matcher m = LITERAL.matcher(domain);
        if (m.lookingAt()) {
            String ip = m.group(1);
            return ip.matches("(\\d{1,3}\\.){3}\\d{1,3}") || ip.contains(":");
        }
        return false;
    }
}
