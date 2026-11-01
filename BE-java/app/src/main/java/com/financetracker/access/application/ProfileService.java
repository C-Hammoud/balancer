package com.financetracker.access.application;

import java.math.BigDecimal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.financetracker.access.api.UserLocale;
import com.financetracker.access.domain.AccessRepositories.UserPreferencesRepository;
import com.financetracker.access.domain.AccessRepositories.UserProfileRepository;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.access.domain.UserPreferences;
import com.financetracker.access.domain.UserProfile;
import com.financetracker.notifications.api.EmailRecipient;
import com.financetracker.shared.locale.LocaleDefaults;
import com.financetracker.shared.web.Py;

/** Port of api/user_profile.py, api/user_preferences.py and UserProfileSerializer output. */
@Service
public class ProfileService {

    private final UserProfileRepository profiles;
    private final UserPreferencesRepository preferences;
    private final Clock clock;

    public ProfileService(UserProfileRepository profiles, UserPreferencesRepository preferences, Clock clock) {
        this.profiles = profiles;
        this.preferences = preferences;
        this.clock = clock;
    }

    /** get_user_profile: get_or_create. */
    @Transactional
    public UserProfile profile(UserAccount user) {
        return profiles.findById(user.getId()).orElseGet(() -> profiles.save(new UserProfile(user.getId())));
    }

    public boolean isEmailVerified(UserAccount user) {
        if (user == null || user.getId() == null) {
            return false;
        }
        return profiles.findById(user.getId()).map(UserProfile::isEmailVerified).orElse(false);
    }

    @Transactional
    public void markEmailVerified(UserAccount user) {
        UserProfile p = profile(user);
        if (!p.isEmailVerified()) {
            p.setEmailVerified(true);
            p.setEmailVerifiedAt(Instant.now(clock));
            profiles.save(p);
        }
    }

    @Transactional
    public void markEmailUnverified(UserAccount user) {
        UserProfile p = profile(user);
        if (p.isEmailVerified() || p.getEmailVerifiedAt() != null) {
            p.setEmailVerified(false);
            p.setEmailVerifiedAt(null);
            profiles.save(p);
        }
    }

    @Transactional
    public void setEmailVerifiedFlag(UserAccount user, boolean verified) {
        UserProfile p = profile(user);
        p.setEmailVerified(verified);
        profiles.save(p);
    }

    /** apply_profile_setup_patch(user, request.data). */
    @Transactional
    public UserProfile applySetupPatch(UserAccount user, Map<String, Object> data) {
        UserProfile p = profile(user);
        Instant now = Instant.now(clock);
        Object status = data.get("setup_status");
        if (UserProfile.SETUP_COMPLETE.equals(status)) {
            p.setSetupStatus(UserProfile.SETUP_COMPLETE);
            p.setSetupCompletedAt(now);
        } else if (UserProfile.SETUP_INCOMPLETE.equals(status)) {
            p.setSetupStatus(UserProfile.SETUP_INCOMPLETE);
            p.setSetupSkippedAt(now);
            if (p.isNotifySetupNudges()) {
                if (p.getSetupNudgePushDueAt() == null) {
                    p.setSetupNudgePushDueAt(now.plus(Duration.ofHours(24)));
                }
                if (p.getSetupNudgeEmailDueAt() == null) {
                    p.setSetupNudgeEmailDueAt(now.plus(Duration.ofHours(48)));
                }
            }
        }
        if (data.containsKey("phone")) {
            Object raw = data.get("phone");
            String phone = Py.truthy(raw) ? Py.str(raw).strip() : "";
            p.setPhone(phone.codePointCount(0, phone.length()) > 32
                    ? phone.substring(0, phone.offsetByCodePoints(0, 32)) : phone);
        }
        if (data.containsKey("notify_weekly_summaries")) {
            p.setNotifyWeeklySummaries(Py.truthy(data.get("notify_weekly_summaries")));
        }
        if (data.containsKey("notify_low_balance")) {
            p.setNotifyLowBalance(Py.truthy(data.get("notify_low_balance")));
        }
        if (data.containsKey("notify_setup_nudges")) {
            p.setNotifySetupNudges(Py.truthy(data.get("notify_setup_nudges")));
        }
        if (data.containsKey("notify_plan_updates")) {
            p.setNotifyPlanUpdates(Py.truthy(data.get("notify_plan_updates")));
        }
        if (data.containsKey("savings_target_pct")) {
            Integer pct = pyInt(data.get("savings_target_pct"));
            int value = pct == null ? p.getSavingsTargetPct() : pct;
            p.setSavingsTargetPct(Math.max(0, Math.min(value, 90)));
        }
        return profiles.save(p);
    }

    /** setup_payload(user). */
    public Map<String, Object> setupPayload(UserAccount user) {
        UserProfile p = profile(user);
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("phone", p.getPhone() == null ? "" : p.getPhone());
        m.put("setup_status", p.getSetupStatus() == null || p.getSetupStatus().isEmpty()
                ? UserProfile.SETUP_PENDING : p.getSetupStatus());
        m.put("notify_weekly_summaries", p.isNotifyWeeklySummaries());
        m.put("notify_low_balance", p.isNotifyLowBalance());
        m.put("notify_setup_nudges", p.isNotifySetupNudges());
        m.put("notify_plan_updates", p.isNotifyPlanUpdates());
        m.put("savings_target_pct", p.getSavingsTargetPct());
        return m;
    }

    /** UserProfileSerializer(user).data. */
    public Map<String, Object> profileJson(UserAccount user) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("id", user.getId());
        m.put("username", user.getUsername());
        m.put("email", user.getEmail());
        m.put("first_name", user.getFirstName());
        m.put("last_name", user.getLastName());
        m.putAll(locale(user.userId()).toMap());
        m.put("email_verified", isEmailVerified(user));
        m.putAll(setupPayload(user));
        return m;
    }

    /** get_user_preferences(user). */
    public UserLocale locale(String userId) {
        return preferences.findById(userId)
                .map(p -> new UserLocale(p.getTimezone(), p.getCountry(), LocaleDefaults.normalizeCurrency(p.getDefaultCurrency())))
                .orElseGet(() -> new UserLocale("", "", "USD"));
    }

    /** save_user_preferences(user, data): only keys present in data change. */
    @Transactional
    public UserLocale savePreferences(String userId, Map<String, Object> patch) {
        UserPreferences prefs = preferences.findById(userId).orElseGet(() -> new UserPreferences(userId));
        LocaleDefaults.Detected merged = LocaleDefaults.detect(
                patch.containsKey("timezone") ? str(patch.get("timezone")) : prefs.getTimezone(),
                null,
                patch.containsKey("country") ? str(patch.get("country")) : prefs.getCountry(),
                patch.containsKey("default_currency") ? str(patch.get("default_currency")) : prefs.getDefaultCurrency());
        prefs.setTimezone(merged.timezone());
        prefs.setCountry(merged.country());
        prefs.setDefaultCurrency(merged.defaultCurrency());
        prefs.setUpdatedAt(Instant.now(clock));
        preferences.save(prefs);
        return locale(userId);
    }

    /** ensure_user_preferences(user, timezone=, locale=, country=). */
    @Transactional
    public UserLocale ensurePreferences(String userId, String timezone, String locale, String country) {
        UserPreferences existing = preferences.findById(userId).orElse(null);
        if (existing != null && notEmpty(existing.getDefaultCurrency()) && notEmpty(existing.getTimezone())) {
            return locale(userId);
        }
        LocaleDefaults.Detected detected = LocaleDefaults.detect(timezone, locale, country, null);
        if (existing != null) {
            if (!notEmpty(existing.getTimezone()) && notEmpty(detected.timezone())) {
                existing.setTimezone(detected.timezone());
            }
            if (!notEmpty(existing.getCountry()) && notEmpty(detected.country())) {
                existing.setCountry(detected.country());
            }
            if (!notEmpty(existing.getDefaultCurrency()) || "USD".equals(existing.getDefaultCurrency())) {
                if (!"USD".equals(detected.defaultCurrency()) || !notEmpty(existing.getDefaultCurrency())) {
                    existing.setDefaultCurrency(detected.defaultCurrency());
                }
            }
            existing.setUpdatedAt(Instant.now(clock));
            preferences.save(existing);
        } else {
            UserPreferences created = new UserPreferences(userId);
            created.setTimezone(detected.timezone());
            created.setCountry(detected.country());
            created.setDefaultCurrency(detected.defaultCurrency());
            created.setUpdatedAt(Instant.now(clock));
            preferences.save(created);
        }
        return locale(userId);
    }

    public static EmailRecipient recipient(UserAccount u) {
        return new EmailRecipient(u.getId(), u.getEmail(), u.getFirstName(), u.getLastName(), u.getUsername());
    }

    private static boolean notEmpty(String s) {
        return s != null && !s.isEmpty();
    }

    private static String str(Object v) {
        return v == null ? null : Py.str(v);
    }

    /** Python int(value): ints, floats truncated, numeric strings; None otherwise. */
    private static Integer pyInt(Object v) {
        if (v instanceof Boolean b) {
            return b ? 1 : 0;
        }
        if (v instanceof Number n) {
            return new BigDecimal(n.toString()).intValue();
        }
        if (v instanceof String s) {
            try {
                return Integer.parseInt(s.strip());
            } catch (NumberFormatException e) {
                return null;
            }
        }
        return null;
    }
}
