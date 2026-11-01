package com.financetracker.shared.locale;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** Port of api/constants.py. */
public final class LocaleConstants {

    public record Choice(String code, String label) {
    }

    public static final List<Choice> CURRENCIES = List.of(
            new Choice("USD", "US Dollar"),
            new Choice("LBP", "Lebanese Lira"),
            new Choice("SAR", "Saudi Riyal"));

    public static final List<Choice> COUNTRIES = List.of(
            new Choice("LB", "Lebanon"),
            new Choice("SA", "Saudi Arabia"));

    public static final List<Choice> CONSUMPTION_TYPES = List.of(
            new Choice("market", "Market"),
            new Choice("transport", "Transport"),
            new Choice("food", "Food"),
            new Choice("other", "Other"));

    public static final Set<String> VALID_CURRENCIES = Set.of("USD", "LBP", "SAR");
    public static final Set<String> VALID_COUNTRIES = Set.of("LB", "SA");
    public static final List<String> CURRENCY_CODES = List.of("USD", "LBP", "SAR");
    public static final String DEFAULT_CURRENCY = "USD";

    public static final Map<String, String> TZ_TO_COUNTRY = Map.of(
            "Asia/Beirut", "LB",
            "Asia/Riyadh", "SA");

    public static final Map<String, String> COUNTRY_TO_TZ = Map.of(
            "LB", "Asia/Beirut",
            "SA", "Asia/Riyadh");

    public static final Map<String, String> COUNTRY_TO_CURRENCY = Map.of(
            "LB", "LBP",
            "SA", "SAR");

    /** IANA timezone to default currency (api/locale_defaults.py TZ_TO_CURRENCY). */
    public static final Map<String, String> TZ_TO_CURRENCY;

    /** BCP-47 locale region to country. */
    public static final Map<String, String> LOCALE_REGION_TO_COUNTRY = Map.of(
            "LB", "LB",
            "SA", "SA",
            "US", "US",
            "GB", "US",
            "AE", "SA");

    static {
        Map<String, String> m = new LinkedHashMap<>();
        m.put("Asia/Beirut", "LBP");
        m.put("Asia/Riyadh", "SAR");
        m.put("Asia/Dubai", "SAR");
        m.put("America/New_York", "USD");
        m.put("America/Los_Angeles", "USD");
        m.put("Europe/London", "USD");
        m.put("UTC", "USD");
        TZ_TO_CURRENCY = Map.copyOf(m);
    }

    private LocaleConstants() {
    }
}
