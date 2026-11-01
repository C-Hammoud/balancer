package com.financetracker.access.domain;

import java.util.List;
import java.util.Optional;

/**
 * Repository ports of the access module. Method names follow Spring Data conventions so the JPA
 * adapter is a bare interface; the Firestore adapter implements them by hand.
 */
public final class AccessRepositories {

    private AccessRepositories() {
    }

    public interface UserAccountRepository {

        Optional<UserAccount> findById(Long id);

        /** Exact, case-sensitive match (Django get_by_natural_key). */
        Optional<UserAccount> findByUsername(String username);

        boolean existsByUsername(String username);

        Optional<UserAccount> findFirstByUsernameIgnoreCaseOrderByIdAsc(String username);

        Optional<UserAccount> findFirstByEmailIgnoreCaseOrderByIdAsc(String email);

        List<UserAccount> findAllByOrderByIdAsc();

        UserAccount save(UserAccount user);
    }

    public interface UserProfileRepository {

        Optional<UserProfile> findById(Long userId);

        List<UserProfile> findBySetupStatusAndNotifySetupNudgesTrue(String setupStatus);

        UserProfile save(UserProfile profile);
    }

    public interface UserPreferencesRepository {

        Optional<UserPreferences> findById(String userId);

        UserPreferences save(UserPreferences preferences);
    }

    public interface RefreshTokenRepository {

        Optional<RefreshTokenRecord> findById(String jti);

        RefreshTokenRecord save(RefreshTokenRecord token);
    }
}
