package com.financetracker.access.api;

import java.util.List;
import java.util.Optional;

/**
 * Everything other modules may ask about users. When the modules become separate services this
 * interface becomes a REST client of the access manager.
 */
public interface UserDirectory {

    Optional<UserSummary> findById(String userId);

    /** First user (lowest id) whose email matches, ignoring case (Django email__iexact .first()). */
    Optional<UserSummary> findByEmail(String email);

    /** All users, ordered by id (used by the scheduled jobs). */
    List<UserSummary> findAll();

    ProfileSettings profileSettings(String userId);

    UserLocale locale(String userId);

    /** api.currency.resolve_report_currency: valid query override, else the saved default. */
    String reportCurrency(String userId, String queryValue);
}
