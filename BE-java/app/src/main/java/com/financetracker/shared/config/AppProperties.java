package com.financetracker.shared.config;

import java.math.BigDecimal;
import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Application settings. Defaults mirror BE/finance_tracker/settings.py; application.yml maps the
 * same environment variable names the Django backend uses, so one .env file serves both.
 */
@ConfigurationProperties(prefix = "app")
public class AppProperties {

    /** "jpa" (any relational database via spring.datasource.*) or "firestore". */
    private DataStoreType datastore = DataStoreType.JPA;
    private boolean debug = false;
    /** Django SECRET_KEY: signs JWTs and email/password-reset tokens. */
    private String secretKey = "";
    private String frontendUrl = "http://localhost:4200";
    private String apiPublicUrl = "http://127.0.0.1:8000/api/v1";
    private String mobileAppScheme = "financetracker";
    private boolean requireEmailVerification = true;
    /** Django PASSWORD_RESET_TIMEOUT (3 days); also bounds email verification links. */
    private Duration passwordResetTimeout = Duration.ofDays(3);
    private Map<String, BigDecimal> exchangeRates = new LinkedHashMap<>();
    /** Optional JSON override, e.g. {"LBP": 0.0000112} (EXCHANGE_RATES). */
    private String exchangeRatesJson = "";
    private String exchangeRatesAsOf = "2026-10-18";
    /** CORS_ALLOWED_ORIGINS (comma separated). In debug every origin is allowed, as in Django. */
    private List<String> corsAllowedOrigins = new ArrayList<>(List.of("http://localhost:4200"));
    /** PBKDF2 iterations for new password hashes (Django 5.2 default). */
    private int passwordHashIterations = 1_000_000;

    private final Jwt jwt = new Jwt();
    private final Email email = new Email();
    private final Throttle throttle = new Throttle();
    private final Import importLimits = new Import();
    private final Firebase firebase = new Firebase();
    private final Jobs jobs = new Jobs();

    public static class Jwt {
        private Duration accessTokenLifetime = Duration.ofMinutes(60);
        private Duration refreshTokenLifetime = Duration.ofDays(7);
        /** Defaults to the secret key, like simplejwt's SIGNING_KEY. */
        private String signingKey = "";

        public Duration getAccessTokenLifetime() { return accessTokenLifetime; }
        public void setAccessTokenLifetime(Duration v) { this.accessTokenLifetime = v; }
        public Duration getRefreshTokenLifetime() { return refreshTokenLifetime; }
        public void setRefreshTokenLifetime(Duration v) { this.refreshTokenLifetime = v; }
        public String getSigningKey() { return signingKey; }
        public void setSigningKey(String v) { this.signingKey = v; }
    }

    public static class Email {
        /** SMTP host; when blank, emails are written to the log (Django console backend). */
        private String host = "";
        private int port = 587;
        private String username = "";
        private String password = "";
        private boolean useTls = true;
        private String from = "noreply@financetracker.local";
        private String appName = "Finance Tracker";
        private String supportEmail = "";
        private String brandPrimary = "#0f3d3e";
        private String brandAccent = "#1a7f7a";
        /** EMAIL_ENABLED=false: never send real email, even with a host; emails go to the log. */
        private boolean enabled = true;
        /**
         * NOTIFICATION_EMAILS_ENABLED=false: account emails (verification, password reset, invites)
         * are still sent; automatic notices (alerts, reminders, plan suggestions, nudges) go to the log.
         */
        private boolean notificationsEnabled = true;

        public boolean isEnabled() { return enabled; }
        public void setEnabled(boolean v) { this.enabled = v; }
        public boolean isNotificationsEnabled() { return notificationsEnabled; }
        public void setNotificationsEnabled(boolean v) { this.notificationsEnabled = v; }
        public String getHost() { return host; }
        public void setHost(String v) { this.host = v; }
        public int getPort() { return port; }
        public void setPort(int v) { this.port = v; }
        public String getUsername() { return username; }
        public void setUsername(String v) { this.username = v; }
        public String getPassword() { return password; }
        public void setPassword(String v) { this.password = v; }
        public boolean isUseTls() { return useTls; }
        public void setUseTls(boolean v) { this.useTls = v; }
        public String getFrom() { return from; }
        public void setFrom(String v) { this.from = v; }
        public String getAppName() { return appName; }
        public void setAppName(String v) { this.appName = v; }
        public String getSupportEmail() { return supportEmail; }
        public void setSupportEmail(String v) { this.supportEmail = v; }
        public String getBrandPrimary() { return brandPrimary; }
        public void setBrandPrimary(String v) { this.brandPrimary = v; }
        public String getBrandAccent() { return brandAccent; }
        public void setBrandAccent(String v) { this.brandAccent = v; }
    }

    /** DRF DEFAULT_THROTTLE_RATES, e.g. "10/min". */
    public static class Throttle {
        private String authLogin = "10/min";
        private String authRegister = "5/hour";
        private String authEmail = "5/hour";
        private String userLookup = "30/hour";

        public String getAuthLogin() { return authLogin; }
        public void setAuthLogin(String v) { this.authLogin = v; }
        public String getAuthRegister() { return authRegister; }
        public void setAuthRegister(String v) { this.authRegister = v; }
        public String getAuthEmail() { return authEmail; }
        public void setAuthEmail(String v) { this.authEmail = v; }
        public String getUserLookup() { return userLookup; }
        public void setUserLookup(String v) { this.userLookup = v; }
    }

    public static class Import {
        private long maxBytes = 5L * 1024 * 1024;
        private int maxRows = 5000;

        public long getMaxBytes() { return maxBytes; }
        public void setMaxBytes(long v) { this.maxBytes = v; }
        public int getMaxRows() { return maxRows; }
        public void setMaxRows(int v) { this.maxRows = v; }
    }

    public static class Firebase {
        private String keyPath = "";
        private String projectId = "";
        private String storageBucket = "";

        public String getKeyPath() { return keyPath; }
        public void setKeyPath(String v) { this.keyPath = v; }
        public String getProjectId() { return projectId; }
        public void setProjectId(String v) { this.projectId = v; }
        public String getStorageBucket() { return storageBucket; }
        public void setStorageBucket(String v) { this.storageBucket = v; }
    }

    /** Scheduled jobs that replace the Django management commands. */
    public static class Jobs {
        private boolean enabled = true;

        public boolean isEnabled() { return enabled; }
        public void setEnabled(boolean v) { this.enabled = v; }
    }

    public DataStoreType getDatastore() { return datastore; }
    public void setDatastore(DataStoreType v) { this.datastore = v; }
    public boolean isDebug() { return debug; }
    public void setDebug(boolean v) { this.debug = v; }
    /** settings.SECRET_KEY: required unless debug, where Django falls back to an insecure dev key. */
    public String getSecretKey() {
        if (secretKey == null || secretKey.isBlank()) {
            if (!debug) {
                throw new IllegalStateException("DJANGO_SECRET_KEY must be set when DJANGO_DEBUG is not 1.");
            }
            return "django-insecure-local-dev-only-do-not-use-in-production";
        }
        return secretKey;
    }
    public void setSecretKey(String v) { this.secretKey = v; }
    public String getFrontendUrl() { return stripTrailingSlash(frontendUrl); }
    public void setFrontendUrl(String v) { this.frontendUrl = v; }
    public String getApiPublicUrl() { return stripTrailingSlash(apiPublicUrl); }
    public void setApiPublicUrl(String v) { this.apiPublicUrl = v; }
    public String getMobileAppScheme() { return mobileAppScheme; }
    public void setMobileAppScheme(String v) { this.mobileAppScheme = v; }
    public boolean isRequireEmailVerification() { return requireEmailVerification; }
    public void setRequireEmailVerification(boolean v) { this.requireEmailVerification = v; }
    public Duration getPasswordResetTimeout() { return passwordResetTimeout; }
    public void setPasswordResetTimeout(Duration v) { this.passwordResetTimeout = v; }
    public Map<String, BigDecimal> getExchangeRates() { return exchangeRates; }
    public void setExchangeRates(Map<String, BigDecimal> v) { this.exchangeRates = v; }
    public String getExchangeRatesJson() { return exchangeRatesJson; }
    public void setExchangeRatesJson(String v) { this.exchangeRatesJson = v; }
    public String getExchangeRatesAsOf() { return exchangeRatesAsOf; }
    public void setExchangeRatesAsOf(String v) { this.exchangeRatesAsOf = v; }
    public List<String> getCorsAllowedOrigins() { return corsAllowedOrigins; }
    public void setCorsAllowedOrigins(List<String> v) { this.corsAllowedOrigins = v; }
    public int getPasswordHashIterations() { return passwordHashIterations; }
    public void setPasswordHashIterations(int v) { this.passwordHashIterations = v; }
    public Jwt getJwt() { return jwt; }
    public Email getEmail() { return email; }
    public Throttle getThrottle() { return throttle; }
    public Import getImportLimits() { return importLimits; }
    public Firebase getFirebase() { return firebase; }
    public Jobs getJobs() { return jobs; }

    private static String stripTrailingSlash(String url) {
        String u = url == null ? "" : url.trim();
        while (u.endsWith("/")) {
            u = u.substring(0, u.length() - 1);
        }
        return u;
    }
}
