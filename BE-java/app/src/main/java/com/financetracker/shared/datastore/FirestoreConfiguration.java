package com.financetracker.shared.datastore;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;

import com.financetracker.shared.config.AppProperties;
import com.financetracker.shared.config.DataStoreType;
import com.google.cloud.NoCredentials;
import com.google.cloud.firestore.Firestore;
import com.google.cloud.firestore.FirestoreOptions;
import com.google.firebase.cloud.FirestoreClient;

/** Beans that exist only when app.datastore=firestore. */
@Configuration(proxyBeanMethods = false)
@ConditionalOnDataStore(DataStoreType.FIRESTORE)
class FirestoreConfiguration {

    /**
     * Firestore client. FIRESTORE_EMULATOR_HOST + app.firebase.project-id selects the local
     * emulator (no key needed); otherwise the service-account key is required.
     */
    @Bean(destroyMethod = "close")
    Firestore firestore(FirebaseSupport firebase, AppProperties props) {
        String emulator = System.getenv("FIRESTORE_EMULATOR_HOST");
        if (emulator != null && !emulator.isBlank()) {
            return FirestoreOptions.newBuilder()
                    .setProjectId(props.getFirebase().getProjectId().isBlank() ? "demo-finance-tracker"
                            : props.getFirebase().getProjectId())
                    .setEmulatorHost(emulator)
                    .setCredentials(NoCredentials.getInstance())
                    .build()
                    .getService();
        }
        return FirestoreClient.getFirestore(firebase.app().orElseThrow(() -> new IllegalStateException(
                "app.datastore=firestore but no Firebase key was found. Set FIREBASE_KEY_PATH, or "
                        + "DATA_STORE=jpa for a relational database.")));
    }

    /**
     * Firestore has no JPA transaction manager; services keep their @Transactional annotations
     * (meaningful in JPA mode) and run without one here, as the Django Firestore code did.
     */
    @Bean
    PlatformTransactionManager transactionManager() {
        return new AbstractPlatformTransactionManager() {
            @Override
            protected Object doGetTransaction() {
                return new Object();
            }

            @Override
            protected void doBegin(Object transaction, TransactionDefinition definition) {
            }

            @Override
            protected void doCommit(DefaultTransactionStatus status) {
            }

            @Override
            protected void doRollback(DefaultTransactionStatus status) {
            }
        };
    }
}
