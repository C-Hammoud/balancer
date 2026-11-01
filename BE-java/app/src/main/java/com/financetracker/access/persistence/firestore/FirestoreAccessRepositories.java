package com.financetracker.access.persistence.firestore;

import static com.financetracker.shared.datastore.FirestoreDocs.await;
import static com.financetracker.shared.datastore.FirestoreDocs.bool;
import static com.financetracker.shared.datastore.FirestoreDocs.instant;
import static com.financetracker.shared.datastore.FirestoreDocs.integer;
import static com.financetracker.shared.datastore.FirestoreDocs.str;
import static com.financetracker.shared.datastore.FirestoreDocs.ts;

import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Repository;

import com.financetracker.access.domain.AccessRepositories.RefreshTokenRepository;
import com.financetracker.access.domain.AccessRepositories.UserPreferencesRepository;
import com.financetracker.access.domain.AccessRepositories.UserProfileRepository;
import com.financetracker.access.domain.RefreshTokenRecord;
import com.financetracker.access.domain.UserPreferences;
import com.financetracker.access.domain.UserProfile;
import com.financetracker.shared.config.DataStoreType;
import com.financetracker.shared.datastore.ConditionalOnDataStore;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;

/** Firestore adapters for profiles, locale preferences and refresh tokens. */
final class FirestoreAccessRepositories {

    private FirestoreAccessRepositories() {
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class Profiles implements UserProfileRepository {

        private static final String COLLECTION = "auth_user_profiles";
        private final Firestore db;

        Profiles(Firestore db) {
            this.db = db;
        }

        @Override
        public Optional<UserProfile> findById(Long userId) {
            DocumentSnapshot doc = await(db.collection(COLLECTION).document(String.valueOf(userId)).get());
            return doc.exists() ? Optional.of(fromDoc(doc)) : Optional.empty();
        }

        @Override
        public List<UserProfile> findBySetupStatusAndNotifySetupNudgesTrue(String setupStatus) {
            return await(db.collection(COLLECTION)
                    .whereEqualTo("setup_status", setupStatus)
                    .whereEqualTo("notify_setup_nudges", true)
                    .get()).getDocuments().stream().map(Profiles::fromDoc).toList();
        }

        @Override
        public UserProfile save(UserProfile p) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", String.valueOf(p.getUserId()));
            d.put("email_verified", p.isEmailVerified());
            d.put("email_verified_at", ts(p.getEmailVerifiedAt()));
            d.put("phone", p.getPhone());
            d.put("setup_status", p.getSetupStatus());
            d.put("setup_skipped_at", ts(p.getSetupSkippedAt()));
            d.put("setup_completed_at", ts(p.getSetupCompletedAt()));
            d.put("setup_nudge_push_due_at", ts(p.getSetupNudgePushDueAt()));
            d.put("setup_nudge_email_due_at", ts(p.getSetupNudgeEmailDueAt()));
            d.put("setup_nudge_push_sent_at", ts(p.getSetupNudgePushSentAt()));
            d.put("setup_nudge_email_sent_at", ts(p.getSetupNudgeEmailSentAt()));
            d.put("notify_weekly_summaries", p.isNotifyWeeklySummaries());
            d.put("notify_low_balance", p.isNotifyLowBalance());
            d.put("notify_setup_nudges", p.isNotifySetupNudges());
            d.put("notify_plan_updates", p.isNotifyPlanUpdates());
            d.put("savings_target_pct", p.getSavingsTargetPct());
            await(db.collection(COLLECTION).document(String.valueOf(p.getUserId())).set(d));
            return p;
        }

        private static UserProfile fromDoc(DocumentSnapshot doc) {
            Map<String, Object> d = doc.getData();
            UserProfile p = new UserProfile(Long.valueOf(doc.getId()));
            p.setEmailVerified(bool(d, "email_verified", false));
            p.setEmailVerifiedAt(instant(d, "email_verified_at"));
            p.setPhone(str(d, "phone"));
            String status = str(d, "setup_status");
            p.setSetupStatus(status.isEmpty() ? UserProfile.SETUP_PENDING : status);
            p.setSetupSkippedAt(instant(d, "setup_skipped_at"));
            p.setSetupCompletedAt(instant(d, "setup_completed_at"));
            p.setSetupNudgePushDueAt(instant(d, "setup_nudge_push_due_at"));
            p.setSetupNudgeEmailDueAt(instant(d, "setup_nudge_email_due_at"));
            p.setSetupNudgePushSentAt(instant(d, "setup_nudge_push_sent_at"));
            p.setSetupNudgeEmailSentAt(instant(d, "setup_nudge_email_sent_at"));
            p.setNotifyWeeklySummaries(bool(d, "notify_weekly_summaries", true));
            p.setNotifyLowBalance(bool(d, "notify_low_balance", true));
            p.setNotifySetupNudges(bool(d, "notify_setup_nudges", true));
            p.setNotifyPlanUpdates(bool(d, "notify_plan_updates", true));
            p.setSavingsTargetPct(d != null && d.containsKey("savings_target_pct") ? integer(d, "savings_target_pct") : 20);
            return p;
        }
    }

    /** Same collection and fields as the Django UserPreferencesFS ("user_preferences"). */
    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class Preferences implements UserPreferencesRepository {

        private static final String COLLECTION = "user_preferences";
        private final Firestore db;

        Preferences(Firestore db) {
            this.db = db;
        }

        @Override
        public Optional<UserPreferences> findById(String userId) {
            DocumentSnapshot doc = await(db.collection(COLLECTION).document(userId).get());
            if (!doc.exists()) {
                return Optional.empty();
            }
            Map<String, Object> d = doc.getData();
            String uid = str(d, "user_id");
            UserPreferences p = new UserPreferences(uid.isEmpty() ? doc.getId() : uid);
            p.setTimezone(str(d, "timezone"));
            p.setCountry(str(d, "country"));
            String cur = str(d, "default_currency");
            p.setDefaultCurrency(cur.isEmpty() ? "USD" : cur);
            p.setUpdatedAt(instant(d, "updated_at"));
            return Optional.of(p);
        }

        @Override
        public UserPreferences save(UserPreferences p) {
            p.setUpdatedAt(Instant.now());
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", p.getUserId());
            d.put("timezone", p.getTimezone());
            d.put("country", p.getCountry());
            d.put("default_currency", p.getDefaultCurrency());
            d.put("updated_at", ts(p.getUpdatedAt()));
            await(db.collection(COLLECTION).document(p.getUserId()).set(d));
            return p;
        }
    }

    @Repository
    @ConditionalOnDataStore(DataStoreType.FIRESTORE)
    static class RefreshTokens implements RefreshTokenRepository {

        private static final String COLLECTION = "auth_refresh_tokens";
        private final Firestore db;

        RefreshTokens(Firestore db) {
            this.db = db;
        }

        @Override
        public Optional<RefreshTokenRecord> findById(String jti) {
            DocumentSnapshot doc = await(db.collection(COLLECTION).document(jti).get());
            if (!doc.exists()) {
                return Optional.empty();
            }
            Map<String, Object> d = doc.getData();
            String uid = str(d, "user_id");
            RefreshTokenRecord r = new RefreshTokenRecord(doc.getId(), uid.isEmpty() ? null : Long.valueOf(uid),
                    str(d, "token"), instant(d, "created_at"), instant(d, "expires_at"));
            r.setBlacklistedAt(instant(d, "blacklisted_at"));
            return Optional.of(r);
        }

        @Override
        public RefreshTokenRecord save(RefreshTokenRecord r) {
            Map<String, Object> d = new HashMap<>();
            d.put("user_id", r.getUserId() == null ? "" : String.valueOf(r.getUserId()));
            d.put("token", r.getToken());
            d.put("created_at", ts(r.getCreatedAt()));
            d.put("expires_at", ts(r.getExpiresAt()));
            d.put("blacklisted_at", ts(r.getBlacklistedAt()));
            await(db.collection(COLLECTION).document(r.getJti()).set(d));
            return r;
        }
    }
}
