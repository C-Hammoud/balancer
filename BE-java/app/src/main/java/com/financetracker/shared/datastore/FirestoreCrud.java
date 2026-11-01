package com.financetracker.shared.datastore;

import static com.financetracker.shared.datastore.FirestoreDocs.await;

import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;

import com.google.cloud.firestore.CollectionReference;
import com.google.cloud.firestore.DocumentSnapshot;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.Query;
import com.google.cloud.firestore.QueryDocumentSnapshot;

/**
 * Base for Firestore adapters: one collection, documents mapped by hand so the field names and
 * value formats stay identical to what the Django code wrote. Results come back ordered by
 * document id, like Firestore's default ordering and the JPA adapters' "OrderByIdAsc".
 */
public abstract class FirestoreCrud<T extends StoredEntity> {

    protected final Firestore db;
    private final String collection;

    protected FirestoreCrud(Firestore db, String collection) {
        this.db = db;
        this.collection = collection;
    }

    protected abstract Map<String, Object> toDoc(T entity);

    protected abstract T fromDoc(String id, Map<String, Object> data);

    protected CollectionReference col() {
        return db.collection(collection);
    }

    public Optional<T> findById(String id) {
        if (id == null || id.isEmpty() || id.contains("/")) {
            return Optional.empty();
        }
        DocumentSnapshot doc = await(col().document(id).get());
        return doc.exists() ? Optional.of(load(doc.getId(), doc.getData())) : Optional.empty();
    }

    public T save(T entity) {
        entity.beforeSave(Instant.now());
        await(col().document(entity.id).set(toDoc(entity)));
        entity.markLoaded();
        return entity;
    }

    public void delete(T entity) {
        if (entity != null && entity.id != null) {
            await(col().document(entity.id).delete());
        }
    }

    /** Every document in the collection. */
    protected List<T> all() {
        return run(col());
    }

    /** Documents matching every (field, value) equality pair. */
    protected List<T> where(Object... fieldValuePairs) {
        Query q = col();
        for (int i = 0; i + 1 < fieldValuePairs.length; i += 2) {
            q = q.whereEqualTo((String) fieldValuePairs[i], fieldValuePairs[i + 1]);
        }
        return run(q);
    }

    protected boolean exists(Object... fieldValuePairs) {
        Query q = col();
        for (int i = 0; i + 1 < fieldValuePairs.length; i += 2) {
            q = q.whereEqualTo((String) fieldValuePairs[i], fieldValuePairs[i + 1]);
        }
        return !await(q.limit(1).get()).isEmpty();
    }

    private List<T> run(Query q) {
        List<QueryDocumentSnapshot> docs = await(q.get()).getDocuments();
        return docs.stream()
                .sorted(Comparator.comparing(DocumentSnapshot::getId))
                .map(d -> load(d.getId(), d.getData()))
                .toList();
    }

    private T load(String id, Map<String, Object> data) {
        T e = fromDoc(id, data);
        e.id = id;
        e.markLoaded();
        return e;
    }
}
