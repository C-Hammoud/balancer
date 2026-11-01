package com.financetracker.access.api;

import java.util.LinkedHashMap;
import java.util.Map;

/** api.user_preferences.get_user_preferences(): {"timezone", "country", "default_currency"}. */
public record UserLocale(String timezone, String country, String defaultCurrency) {

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("timezone", timezone);
        m.put("country", country);
        m.put("default_currency", defaultCurrency);
        return m;
    }
}
