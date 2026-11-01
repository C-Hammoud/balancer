package com.financetracker.shared.datastore;

import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

import com.financetracker.shared.config.AppProperties;
import com.google.auth.oauth2.GoogleCredentials;
import com.google.firebase.FirebaseApp;
import com.google.firebase.FirebaseOptions;

/**
 * Initialises the Firebase Admin SDK from the service-account key (port of firebase_client.py).
 * Used for Firebase login in every mode and for Firestore when app.datastore=firestore.
 */
@Component
public class FirebaseSupport {

    private static final Logger log = LoggerFactory.getLogger(FirebaseSupport.class);
    private static final String KEY_FILE = "finance-tracker-firebase_key.json";

    private final AppProperties props;
    private volatile FirebaseApp app;
    private volatile boolean attempted;

    public FirebaseSupport(AppProperties props) {
        this.props = props;
    }

    /** The initialised app, or empty when no key file is available. */
    public Optional<FirebaseApp> app() {
        if (!attempted) {
            synchronized (this) {
                if (!attempted) {
                    app = initialise();
                    attempted = true;
                }
            }
        }
        return Optional.ofNullable(app);
    }

    public Optional<Path> keyPath() {
        List<Path> candidates = new ArrayList<>();
        String configured = props.getFirebase().getKeyPath();
        if (configured != null && !configured.isBlank()) {
            candidates.add(Path.of(configured.strip()));
        }
        candidates.add(Path.of(KEY_FILE));
        candidates.add(Path.of("resources", KEY_FILE));
        return candidates.stream().filter(Files::isRegularFile).findFirst();
    }

    private FirebaseApp initialise() {
        if (!FirebaseApp.getApps().isEmpty()) {
            return FirebaseApp.getInstance();
        }
        Optional<Path> key = keyPath();
        if (key.isEmpty()) {
            log.info("Firebase key not found; Firebase login is disabled.");
            return null;
        }
        try (InputStream in = new FileInputStream(key.get().toFile())) {
            FirebaseOptions.Builder options = FirebaseOptions.builder()
                    .setCredentials(GoogleCredentials.fromStream(in));
            String bucket = props.getFirebase().getStorageBucket();
            if (bucket != null && !bucket.isBlank()) {
                options.setStorageBucket(bucket);
            }
            String projectId = props.getFirebase().getProjectId();
            if (projectId != null && !projectId.isBlank()) {
                options.setProjectId(projectId);
            }
            return FirebaseApp.initializeApp(options.build());
        } catch (IOException e) {
            log.warn("Could not initialise Firebase from {}: {}", key.get(), e.getMessage());
            return null;
        }
    }
}
