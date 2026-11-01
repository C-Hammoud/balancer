package com.financetracker.access.web;

import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import com.financetracker.access.api.UserLocale;
import com.financetracker.access.application.ProfileService;
import com.financetracker.shared.locale.ExchangeRates;
import com.financetracker.shared.locale.LocaleConstants;
import com.financetracker.shared.locale.LocaleConstants.Choice;
import com.financetracker.shared.locale.LocaleDefaults;
import com.financetracker.shared.security.AuthUser;
import com.financetracker.shared.security.CurrentUser;

/** api/views/meta.py: health checks and locale metadata. */
@RestController
class MetaController {

    private final ProfileService profiles;
    private final ExchangeRates rates;

    MetaController(ProfileService profiles, ExchangeRates rates) {
        this.profiles = profiles;
        this.rates = rates;
    }

    @GetMapping({"/api/v1/health/", "/healthz/"})
    Map<String, Object> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/v1/meta/")
    Map<String, Object> meta(@RequestParam(required = false) String tz, @RequestParam(required = false) String locale,
            @RequestParam(required = false) String country) {
        Map<String, Object> payload = new LinkedHashMap<>();
        payload.put("currencies", choices(LocaleConstants.CURRENCIES));
        payload.put("consumption_types", choices(LocaleConstants.CONSUMPTION_TYPES));
        payload.put("countries", choices(LocaleConstants.COUNTRIES.stream()
                .sorted(Comparator.comparing(Choice::label)).toList()));
        payload.put("suggested", LocaleDefaults.detect(tz, locale, country, null).toMap());
        payload.put("exchange_rates", rates.rates());
        payload.put("exchange_rates_as_of", rates.asOf());
        Optional<AuthUser> user = CurrentUser.get();
        if (user.isPresent()) {
            UserLocale saved = profiles.locale(user.get().userId());
            if (saved.defaultCurrency() != null && !saved.defaultCurrency().isEmpty()) {
                payload.put("suggested", LocaleDefaults.detect(
                        nonEmpty(saved.timezone()) ? saved.timezone() : tz,
                        locale,
                        nonEmpty(saved.country()) ? saved.country() : country,
                        saved.defaultCurrency()).toMap());
                payload.put("saved_preferences", saved.toMap());
            }
        }
        return payload;
    }

    private static List<Map<String, Object>> choices(List<Choice> list) {
        return list.stream().map(c -> {
            Map<String, Object> m = new LinkedHashMap<>();
            m.put("code", c.code());
            m.put("label", c.label());
            return m;
        }).toList();
    }

    private static boolean nonEmpty(String s) {
        return s != null && !s.isEmpty();
    }
}
