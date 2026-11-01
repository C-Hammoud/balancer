package com.financetracker.access.application;

import java.util.List;
import java.util.Optional;

import org.springframework.stereotype.Service;

import com.financetracker.access.api.ProfileSettings;
import com.financetracker.access.api.UserDirectory;
import com.financetracker.access.api.UserLocale;
import com.financetracker.access.api.UserSummary;
import com.financetracker.access.domain.AccessRepositories.UserAccountRepository;
import com.financetracker.access.domain.AccessRepositories.UserProfileRepository;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.access.domain.UserProfile;
import com.financetracker.shared.locale.LocaleConstants;
import com.financetracker.shared.locale.LocaleDefaults;

@Service
class UserDirectoryService implements UserDirectory {

    private final UserAccountRepository users;
    private final UserProfileRepository profiles;
    private final ProfileService profileService;

    UserDirectoryService(UserAccountRepository users, UserProfileRepository profiles, ProfileService profileService) {
        this.users = users;
        this.profiles = profiles;
        this.profileService = profileService;
    }

    @Override
    public Optional<UserSummary> findById(String userId) {
        return parse(userId).flatMap(users::findById).map(UserDirectoryService::summary);
    }

    @Override
    public Optional<UserSummary> findByEmail(String email) {
        if (email == null || email.isBlank()) {
            return Optional.empty();
        }
        return users.findFirstByEmailIgnoreCaseOrderByIdAsc(email.strip()).map(UserDirectoryService::summary);
    }

    @Override
    public List<UserSummary> findAll() {
        return users.findAllByOrderByIdAsc().stream().map(UserDirectoryService::summary).toList();
    }

    @Override
    public ProfileSettings profileSettings(String userId) {
        UserProfile p = parse(userId).flatMap(profiles::findById).orElseGet(() -> new UserProfile(null));
        return new ProfileSettings(p.isEmailVerified(), p.isNotifyWeeklySummaries(), p.isNotifyLowBalance(),
                p.isNotifySetupNudges(), p.isNotifyPlanUpdates(), p.getSavingsTargetPct());
    }

    @Override
    public UserLocale locale(String userId) {
        return profileService.locale(userId);
    }

    @Override
    public String reportCurrency(String userId, String queryValue) {
        if (queryValue != null && !queryValue.isEmpty()) {
            String q = LocaleDefaults.normalizeCurrency(queryValue);
            if (LocaleConstants.VALID_CURRENCIES.contains(q)) {
                return q;
            }
        }
        String saved = locale(userId).defaultCurrency();
        return saved == null || saved.isEmpty() ? "USD" : saved;
    }

    private static Optional<Long> parse(String userId) {
        try {
            return Optional.of(Long.parseLong(userId.strip()));
        } catch (RuntimeException e) {
            return Optional.empty();
        }
    }

    private static UserSummary summary(UserAccount u) {
        return new UserSummary(u.getId(), u.getUsername(), u.getEmail(), u.getFirstName(), u.getLastName(),
                u.isStaff(), u.isActive());
    }
}
