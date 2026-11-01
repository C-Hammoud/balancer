package com.financetracker.access.application;

import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.financetracker.access.domain.AccessRepositories.UserAccountRepository;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.shared.error.ApiException;
import com.financetracker.shared.locale.LocaleConstants;
import com.financetracker.shared.security.AuthUser;
import com.financetracker.shared.web.Field;
import com.financetracker.shared.web.RequestData;

/** Port of MeView (GET / PATCH /auth/me/). */
@Service
public class MeService {

    private final UserAccountRepository users;
    private final ProfileService profiles;
    private final AuthService auth;

    public MeService(UserAccountRepository users, ProfileService profiles, AuthService auth) {
        this.users = users;
        this.profiles = profiles;
        this.auth = auth;
    }

    @Transactional
    public Map<String, Object> get(AuthUser principal, String tz, String locale, String country) {
        UserAccount user = load(principal);
        if (notEmpty(tz) || notEmpty(locale) || notEmpty(country)) {
            profiles.ensurePreferences(user.userId(), tz, locale, country);
        }
        return profiles.profileJson(user);
    }

    @Transactional
    public Map<String, Object> update(AuthUser principal, Map<String, Object> body) {
        UserAccount user = load(principal);
        Map<String, Object> data = body == null ? Map.of() : body;
        String oldEmail = user.getEmail() == null ? "" : user.getEmail().strip().toLowerCase();

        RequestData d = RequestData.partial(data);
        String email = d.email("email", Field.optional().allowBlank().maxLength(254));
        String firstName = d.string("first_name", Field.optional().allowBlank().maxLength(150));
        String lastName = d.string("last_name", Field.optional().allowBlank().maxLength(150));
        String timezone = d.string("timezone", Field.withDefault("").allowBlank());
        String country = d.string("country", Field.withDefault("").allowBlank());
        String currency = d.choice("default_currency", LocaleConstants.CURRENCY_CODES, Field.withDefault("").allowBlank());
        d.validate();

        boolean emailChanged = false;
        boolean userChanged = false;
        if (d.provided("email")) {
            emailChanged = !email.strip().toLowerCase().equals(oldEmail);
            user.setEmail(email);
            userChanged = true;
        }
        if (d.provided("first_name")) {
            user.setFirstName(firstName);
            userChanged = true;
        }
        if (d.provided("last_name")) {
            user.setLastName(lastName);
            userChanged = true;
        }
        if (userChanged) {
            users.save(user);
        }
        if (emailChanged) {
            profiles.markEmailUnverified(user);
            auth.sendVerification(user);
        }

        Map<String, Object> prefPatch = new LinkedHashMap<>();
        if (data.containsKey("timezone")) {
            prefPatch.put("timezone", timezone);
        }
        if (data.containsKey("country")) {
            prefPatch.put("country", country);
        }
        if (data.containsKey("default_currency")) {
            prefPatch.put("default_currency", currency);
        }
        if (!prefPatch.isEmpty()) {
            profiles.savePreferences(user.userId(), prefPatch);
        }
        profiles.applySetupPatch(user, data);
        return profiles.profileJson(user);
    }

    private UserAccount load(AuthUser principal) {
        return users.findById(principal.id()).orElseThrow(() -> ApiException.unauthorized("User not found"));
    }

    private static boolean notEmpty(String s) {
        return s != null && !s.isEmpty();
    }
}
