package com.financetracker.shared.locale;

import static com.financetracker.shared.locale.LocaleConstants.COUNTRY_TO_CURRENCY;
import static com.financetracker.shared.locale.LocaleConstants.COUNTRY_TO_TZ;
import static com.financetracker.shared.locale.LocaleConstants.DEFAULT_CURRENCY;
import static com.financetracker.shared.locale.LocaleConstants.LOCALE_REGION_TO_COUNTRY;
import static com.financetracker.shared.locale.LocaleConstants.TZ_TO_COUNTRY;
import static com.financetracker.shared.locale.LocaleConstants.TZ_TO_CURRENCY;
import static com.financetracker.shared.locale.LocaleConstants.VALID_COUNTRIES;
import static com.financetracker.shared.locale.LocaleConstants.VALID_CURRENCIES;

import java.util.LinkedHashMap;
import java.util.Map;

/** Port of api/locale_defaults.py: detect timezone, country and currency from client hints. */
public final class LocaleDefaults {

    public record Detected(String timezone, String country, String defaultCurrency) {

        public Map<String, Object> toMap() {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("timezone", timezone);
            m.put("country", country);
            m.put("default_currency", defaultCurrency);
            return m;
        }
    }

    private LocaleDefaults() {
    }

    public static String normalizeCurrency(String code) {
        String c = code == null ? "" : code.strip().toUpperCase();
        return VALID_CURRENCIES.contains(c) ? c : DEFAULT_CURRENCY;
    }

    public static String currencyForCountry(String countryCode) {
        String cc = countryCode == null ? "" : countryCode.strip().toUpperCase();
        if (COUNTRY_TO_CURRENCY.containsKey(cc)) {
            return COUNTRY_TO_CURRENCY.get(cc);
        }
        if ("US".equals(cc)) {
            return "USD";
        }
        return DEFAULT_CURRENCY;
    }

    public static String countryFromLocale(String locale) {
        String loc = locale == null ? "" : locale.strip().replace('_', '-');
        if (loc.isEmpty()) {
            return "";
        }
        String[] parts = loc.split("-", -1);
        if (parts.length >= 2) {
            String region = parts[parts.length - 1].toUpperCase();
            if (LOCALE_REGION_TO_COUNTRY.containsKey(region)) {
                return LOCALE_REGION_TO_COUNTRY.get(region);
            }
            if (VALID_COUNTRIES.contains(region)) {
                return region;
            }
        }
        return "";
    }

    /** Merge client hints; saved preferences passed in take precedence over detection. */
    public static Detected detect(String timezone, String locale, String country, String defaultCurrency) {
        String tz = timezone == null ? "" : timezone.strip();
        String cc = country == null ? "" : country.strip().toUpperCase();
        String cur = defaultCurrency != null && !defaultCurrency.isEmpty() ? normalizeCurrency(defaultCurrency) : "";

        if (cc.isEmpty() && TZ_TO_COUNTRY.containsKey(tz)) {
            cc = TZ_TO_COUNTRY.get(tz);
        }
        if (cc.isEmpty()) {
            cc = countryFromLocale(locale);
        }
        if (cur.isEmpty()) {
            if (TZ_TO_CURRENCY.containsKey(tz)) {
                cur = TZ_TO_CURRENCY.get(tz);
            } else if (!cc.isEmpty()) {
                cur = currencyForCountry(cc);
            } else {
                cur = DEFAULT_CURRENCY;
            }
        }
        if (tz.isEmpty() && !cc.isEmpty()) {
            tz = COUNTRY_TO_TZ.getOrDefault(cc, "");
        }
        return new Detected(tz, cc, normalizeCurrency(cur));
    }
}
