package com.financetracker.shared.config;

/**
 * Which adapter backs the repository interfaces. {@code sqlite} is accepted as an alias of
 * {@link #JPA} so an existing Django .env (DATA_STORE=sqlite) keeps working.
 */
public enum DataStoreType {
    JPA,
    FIRESTORE;

    public static DataStoreType parse(String raw) {
        String v = raw == null ? "" : raw.trim().toLowerCase();
        return switch (v) {
            case "firestore" -> FIRESTORE;
            case "", "jpa", "sqlite", "sql", "jdbc" -> JPA;
            default -> throw new IllegalArgumentException("Unknown app.datastore '" + raw + "' (use jpa or firestore)");
        };
    }
}
