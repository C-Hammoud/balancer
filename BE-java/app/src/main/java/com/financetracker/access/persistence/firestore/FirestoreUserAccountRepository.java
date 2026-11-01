package com.financetracker.access.persistence.firestore;

import static com.financetracker.shared.datastore.FirestoreDocs.await;
import static com.financetracker.shared.datastore.FirestoreDocs.bool;
import static com.financetracker.shared.datastore.FirestoreDocs.instant;
import static com.financetracker.shared.datastore.FirestoreDocs.str;
import static com.financetracker.shared.datastore.FirestoreDocs.ts;

import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;

import org.springframework.stereotype.Repository;

import com.financetracker.access.domain.AccessRepositories.UserAccountRepository;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.shared.config.DataStoreType;
import com.financetracker.shared.datastore.ConditionalOnDataStore;
import com.google.cloud.firestore.CollectionReference;
import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.QueryDocumentSnapshot;

/**
 * Users in Firestore ("auth_users", document id = numeric user id). Django kept users in SQLite
 * even in Firestore mode; here they live next to the rest of the data. Numeric ids come from a
 * counter document so ids stay compatible with the clients (user.id is a number).
 */
@Repository
@ConditionalOnDataStore(DataStoreType.FIRESTORE)
class FirestoreUserAccountRepository implements UserAccountRepository {

    static final String COLLECTION = "auth_users";
    private static final String COUNTER = "counters/auth_users";

    private final Firestore db;

    FirestoreUserAccountRepository(Firestore db) {
        this.db = db;
    }

    private CollectionReference col() {
        return db.collection(COLLECTION);
    }

    @Override
    public Optional<UserAccount> findById(Long id) {
        if (id == null) {
            return Optional.empty();
        }
        DocumentSnapshot doc = await(col().document(String.valueOf(id)).get());
        return doc.exists() ? Optional.of(fromDoc(doc)) : Optional.empty();
    }

    @Override
    public Optional<UserAccount> findByUsername(String username) {
        return first(await(col().whereEqualTo("username", username).get()).getDocuments());
    }

    @Override
    public boolean existsByUsername(String username) {
        return !await(col().whereEqualTo("username", username).limit(1).get()).isEmpty();
    }

    @Override
    public Optional<UserAccount> findFirstByUsernameIgnoreCaseOrderByIdAsc(String username) {
        String lower = username == null ? "" : username.toLowerCase(Locale.ROOT);
        return first(await(col().whereEqualTo("username_lower", lower).get()).getDocuments());
    }

    @Override
    public Optional<UserAccount> findFirstByEmailIgnoreCaseOrderByIdAsc(String email) {
        String lower = email == null ? "" : email.toLowerCase(Locale.ROOT);
        return first(await(col().whereEqualTo("email_lower", lower).get()).getDocuments());
    }

    @Override
    public List<UserAccount> findAllByOrderByIdAsc() {
        return await(col().get()).getDocuments().stream()
                .map(FirestoreUserAccountRepository::fromDoc)
                .sorted(Comparator.comparing(UserAccount::getId))
                .toList();
    }

    @Override
    public UserAccount save(UserAccount user) {
        if (user.getId() == null) {
            user.setId(nextId());
        }
        await(col().document(String.valueOf(user.getId())).set(toDoc(user)));
        return user;
    }

    private long nextId() {
        DocumentReference counter = db.document(COUNTER);
        return await(db.runTransaction(tx -> {
            DocumentSnapshot snap = tx.get(counter).get();
            Long current = snap.exists() ? snap.getLong("next") : null;
            long next = current == null ? 1L : current;
            Map<String, Object> data = new HashMap<>();
            data.put("next", next + 1);
            tx.set(counter, data);
            return next;
        }));
    }

    private static Optional<UserAccount> first(List<QueryDocumentSnapshot> docs) {
        return docs.stream().map(FirestoreUserAccountRepository::fromDoc)
                .min(Comparator.comparing(UserAccount::getId));
    }

    static Map<String, Object> toDoc(UserAccount u) {
        Map<String, Object> d = new HashMap<>();
        d.put("username", u.getUsername());
        d.put("username_lower", u.getUsername() == null ? "" : u.getUsername().toLowerCase(Locale.ROOT));
        d.put("email", u.getEmail());
        d.put("email_lower", u.getEmail().toLowerCase(Locale.ROOT));
        d.put("first_name", u.getFirstName());
        d.put("last_name", u.getLastName());
        d.put("password", u.getPassword());
        d.put("is_staff", u.isStaff());
        d.put("is_superuser", u.isSuperuser());
        d.put("is_active", u.isActive());
        d.put("last_login", ts(u.getLastLogin()));
        d.put("date_joined", ts(u.getDateJoined()));
        return d;
    }

    static UserAccount fromDoc(DocumentSnapshot doc) {
        Map<String, Object> d = doc.getData();
        UserAccount u = new UserAccount();
        u.setId(Long.valueOf(doc.getId()));
        u.setUsername(str(d, "username"));
        u.setEmail(str(d, "email"));
        u.setFirstName(str(d, "first_name"));
        u.setLastName(str(d, "last_name"));
        u.setPassword(str(d, "password"));
        u.setStaff(bool(d, "is_staff", false));
        u.setSuperuser(bool(d, "is_superuser", false));
        u.setActive(bool(d, "is_active", true));
        u.setLastLogin(instant(d, "last_login"));
        u.setDateJoined(instant(d, "date_joined"));
        return u;
    }
}
