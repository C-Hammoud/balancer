package com.financetracker.access.application;

import java.text.Normalizer;
import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.regex.Pattern;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import com.financetracker.access.api.EmailVerified;
import com.financetracker.access.domain.AccessRepositories.UserAccountRepository;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.access.security.DjangoPasswordHasher;
import com.financetracker.access.security.DjangoTokenGenerator;
import com.financetracker.access.security.PasswordPolicy;
import com.financetracker.access.security.SimpleJwtTokens;
import com.financetracker.access.security.TokenError;
import com.financetracker.notifications.api.TransactionalEmails;
import com.financetracker.shared.config.AppProperties;
import com.financetracker.shared.datastore.FirebaseSupport;
import com.financetracker.shared.error.ApiException;
import com.financetracker.shared.security.AuthUser;
import com.financetracker.shared.web.Field;
import com.financetracker.shared.web.Py;
import com.financetracker.shared.web.RequestData;
import com.google.cloud.firestore.DocumentReference;
import com.google.cloud.firestore.FieldValue;
import com.google.cloud.firestore.Firestore;
import com.google.firebase.FirebaseApp;
import com.google.firebase.auth.FirebaseAuth;
import com.google.firebase.auth.FirebaseToken;

/** Port of api/views/auth.py (+ serializers and api/email_verification.py). */
@Service
public class AuthService {

    private static final Logger log = LoggerFactory.getLogger(AuthService.class);

    public static final String PASSWORD_RESET_SENT_MSG =
            "If an account exists with that email or username, you will receive password reset instructions shortly.";
    public static final String VERIFICATION_RESENT_MSG =
            "If an unverified account exists for that email, a verification link was sent.";
    private static final String INVALID_LINK = "Invalid or expired verification link.";
    private static final String INVALID_RESET = "Invalid or expired reset link.";
    private static final Pattern USERNAME = Pattern.compile("^[\\w.@+-]+\\z", Pattern.UNICODE_CHARACTER_CLASS);

    public record VerifyResult(boolean ok, String detail) {
    }

    public record Created(Map<String, Object> body) {
    }

    private final UserAccountRepository users;
    private final ProfileService profiles;
    private final DjangoPasswordHasher hasher;
    private final PasswordPolicy passwordPolicy;
    private final SimpleJwtTokens jwt;
    private final DjangoTokenGenerator passwordResetTokens;
    private final DjangoTokenGenerator emailVerificationTokens;
    private final AuthLinks links;
    private final TransactionalEmails emails;
    private final AppProperties props;
    private final ApplicationEventPublisher events;
    private final FirebaseSupport firebase;
    private final ObjectProvider<Firestore> firestore;
    private final Clock clock;

    public AuthService(UserAccountRepository users, ProfileService profiles, DjangoPasswordHasher hasher,
            PasswordPolicy passwordPolicy, SimpleJwtTokens jwt,
            @Qualifier("passwordResetTokens") DjangoTokenGenerator passwordResetTokens,
            @Qualifier("emailVerificationTokens") DjangoTokenGenerator emailVerificationTokens,
            AuthLinks links, TransactionalEmails emails, AppProperties props, ApplicationEventPublisher events,
            FirebaseSupport firebase, ObjectProvider<Firestore> firestore, Clock clock) {
        this.users = users;
        this.profiles = profiles;
        this.hasher = hasher;
        this.passwordPolicy = passwordPolicy;
        this.jwt = jwt;
        this.passwordResetTokens = passwordResetTokens;
        this.emailVerificationTokens = emailVerificationTokens;
        this.links = links;
        this.emails = emails;
        this.props = props;
        this.events = events;
        this.firebase = firebase;
        this.firestore = firestore;
        this.clock = clock;
    }

    // ------------------------------------------------------------------ register

    /** RegisterView.create: 201 with either the verification notice or user + tokens. */
    @Transactional
    public Map<String, Object> register(Map<String, Object> body) {
        RequestData d = RequestData.of(body);
        String username = d.string("username", Field.required());
        if (username != null) {
            if (!USERNAME.matcher(username).matches()) {
                d.errors().add("username", "Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters.");
            }
            if (users.existsByUsername(username)) {
                d.errors().add("username", "A user with that username already exists.");
            }
            if (username.codePointCount(0, username.length()) > 150) {
                d.errors().add("username", "Ensure this field has no more than 150 characters.");
            }
        }
        String email = d.email("email", Field.optional().allowBlank().maxLength(254));
        String firstName = d.string("first_name", Field.optional().allowBlank().maxLength(150));
        String lastName = d.string("last_name", Field.optional().allowBlank().maxLength(150));
        String password = validatedPassword(d, "password");
        String confirm = d.string("password_confirm", Field.required());
        d.validate();
        if (!password.equals(confirm)) {
            throw ApiException.field("password_confirm", "Passwords do not match.");
        }

        UserAccount user = new UserAccount();
        user.setUsername(Normalizer.normalize(username, Normalizer.Form.NFKC));
        user.setEmail(normalizeEmail(email));
        user.setFirstName(firstName);
        user.setLastName(lastName);
        user.setPassword(hasher.encode(password));
        user.setDateJoined(Instant.now(clock));
        user = users.save(user);
        profiles.profile(user);

        boolean emailSent = emails.welcomeAndVerification(ProfileService.recipient(user),
                links.emailVerificationUrl(user), links.mobileVerifyUrl(user));

        Map<String, Object> out = new LinkedHashMap<>();
        if (props.isRequireEmailVerification()) {
            out.put("detail", emailSent
                    ? "Account created. Check your email to verify your address, then sign in."
                    : "Account created, but we could not send the verification email. Contact support or try resending from the sign-in page.");
            out.put("email", user.getEmail());
            out.put("email_sent", emailSent);
            out.put("verification_required", true);
            return out;
        }
        SimpleJwtTokens.Pair tokens = jwt.forUser(user);
        profiles.markEmailVerified(user);
        out.put("user", profiles.profileJson(user));
        out.put("refresh", tokens.refresh());
        out.put("access", tokens.access());
        return out;
    }

    /** CharField + validate_password, errors reported on the field. */
    private String validatedPassword(RequestData d, String key) {
        String password = d.string(key, Field.required());
        if (password != null) {
            List<String> problems = passwordPolicy.validate(password);
            if (!problems.isEmpty()) {
                d.errors().addAll(key, problems);
            }
        }
        return password;
    }

    /** BaseUserManager.normalize_email: lowercase the domain part. */
    static String normalizeEmail(String email) {
        String e = email == null ? "" : email;
        int at = e.strip().lastIndexOf('@');
        if (at < 0) {
            return e;
        }
        String stripped = e.strip();
        return stripped.substring(0, at) + "@" + stripped.substring(at + 1).toLowerCase();
    }

    // ------------------------------------------------------------------ tokens

    /** LoginView (TokenObtainPairView + email verification gate). */
    @Transactional
    public Map<String, Object> login(Map<String, Object> body) {
        RequestData d = RequestData.of(body);
        String username = d.string("username", Field.required());
        String password = d.string("password", Field.required());
        d.validate();

        Optional<UserAccount> found = users.findByUsername(username);
        if (found.isEmpty()) {
            hasher.encode(password); // same cost as a real check (Django runs the hasher once)
            throw noActiveAccount();
        }
        UserAccount user = found.get();
        if (!hasher.matches(password, user.getPassword()) || !user.isActive()) {
            throw noActiveAccount();
        }
        if (hasher.mustUpdate(user.getPassword())) {
            user.setPassword(hasher.encode(password));
            users.save(user);
        }
        SimpleJwtTokens.Pair tokens = jwt.forUser(user);
        if (props.isRequireEmailVerification() && !profiles.isEmailVerified(user)) {
            Map<String, Object> err = new LinkedHashMap<>();
            // Plain strings (not lists): the clients check code === 'email_not_verified'.
            err.put("detail", "Please verify your email before signing in. "
                    + "Check your inbox for the welcome email with the verification link.");
            err.put("code", "email_not_verified");
            throw new ApiException(HttpStatus.BAD_REQUEST, err);
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("refresh", tokens.refresh());
        out.put("access", tokens.access());
        return out;
    }

    private static ApiException noActiveAccount() {
        return ApiException.unauthorized("No active account found with the given credentials");
    }

    /** RefreshTokenView (TokenRefreshView with rotation + blacklist). */
    @Transactional
    public Map<String, Object> refresh(Map<String, Object> body) {
        RequestData d = RequestData.of(body);
        String raw = d.string("refresh", Field.required());
        d.validate();
        Map<String, Object> payload;
        try {
            payload = jwt.validateRefresh(raw);
        } catch (TokenError e) {
            throw invalidToken(e.getMessage());
        }
        Object uid = payload.get("user_id");
        if (uid != null) {
            Optional<UserAccount> user = parseId(String.valueOf(uid)).flatMap(users::findById);
            if (user.isEmpty() || !user.get().isActive()) {
                Map<String, Object> err = new LinkedHashMap<>();
                err.put("detail", "No active account found for the given token.");
                err.put("code", "no_active_account");
                throw ApiException.unauthorized(err);
            }
        }
        return jwt.refresh(payload, raw);
    }

    private static ApiException invalidToken(String message) {
        Map<String, Object> err = new LinkedHashMap<>();
        err.put("detail", message);
        err.put("code", "token_not_valid");
        return ApiException.unauthorized(err);
    }

    /** LogoutView: blacklist the refresh token; already invalid tokens are fine. */
    @Transactional
    public void logout(Map<String, Object> body) {
        Object v = body == null ? null : body.get("refresh");
        String raw = Py.truthy(v) ? Py.str(v).strip() : "";
        if (raw.isEmpty()) {
            throw ApiException.field("refresh", RequestData.REQUIRED);
        }
        try {
            jwt.blacklist(jwt.validateRefresh(raw), raw);
        } catch (TokenError ignored) {
            // Already expired/blacklisted/invalid: the session is over either way.
        }
    }

    // ------------------------------------------------------------------ email verification

    /** verify_email_with_token(uid_b64, raw_token). */
    @Transactional
    public VerifyResult verifyEmail(String uidB64, String rawToken) {
        String token = Py.unquote(rawToken == null ? "" : rawToken.strip());
        if (uidB64 == null || uidB64.isEmpty() || token.isEmpty()) {
            return new VerifyResult(false, INVALID_LINK);
        }
        Optional<UserAccount> user = decodeUid(uidB64).flatMap(users::findById);
        if (user.isEmpty()) {
            log.info("Email verify failed: user lookup");
            return new VerifyResult(false, INVALID_LINK);
        }
        UserAccount u = user.get();
        if (!emailVerificationTokens.checkToken(u, token)) {
            log.info("Email verify failed: bad token for user {}", u.getId());
            return new VerifyResult(false, INVALID_LINK);
        }
        profiles.markEmailVerified(u);
        if (!profiles.isEmailVerified(u)) {
            log.error("Email verify save failed for user {}", u.getId());
            return new VerifyResult(false, "Could not save verification status. Please try again.");
        }
        try {
            events.publishEvent(new EmailVerified(u.userId(), u.getEmail()));
        } catch (RuntimeException e) {
            log.warn("Failed to apply pending budget invites for user {}: {}", u.getId(), e.getMessage());
        }
        return new VerifyResult(true, "Email verified successfully. You can sign in now.");
    }

    /** POST /auth/email-verify/confirm/. */
    @Transactional
    public Map<String, Object> confirmEmail(Map<String, Object> body) {
        RequestData d = RequestData.of(body);
        String uid = d.string("uid", Field.required());
        String token = d.string("token", Field.required());
        d.validate();
        VerifyResult result = verifyEmail(uid, token);
        if (!result.ok()) {
            throw ApiException.badRequest(result.detail());
        }
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("detail", result.detail());
        out.put("email_verified", true);
        return out;
    }

    /** GET /auth/email-verify/confirm/: HTML that hands off to the app or the web page. */
    @Transactional
    public String confirmEmailPage(String uid, String token) {
        VerifyResult result = verifyEmail(uid, token);
        String frontend = props.getFrontendUrl();
        if (result.ok()) {
            return AuthLinks.handoffHtml("Email verified", "Opening Finance Tracker so you can sign in.",
                    links.mobileDeepLink("login", "verified", "1"), frontend + "/login?verified=1");
        }
        String error = Py.quote(result.detail(), "");
        return AuthLinks.handoffHtml("Could not verify email", result.detail(),
                links.mobileDeepLink("verify-email", "uid", uid, "token", token, "error", result.detail()),
                frontend + "/verify-email?uid=" + uid + "&token=" + token + "&error=" + error);
    }

    /** EmailVerifyResendView. */
    @Transactional
    public Map<String, Object> resendVerification(Map<String, Object> body, Optional<AuthUser> current) {
        RequestData d = RequestData.of(body);
        String email = d.email("email", Field.optional().allowBlank());
        d.validate();
        String e = email == null ? "" : email.strip();
        Optional<UserAccount> user = current.isPresent()
                ? users.findById(current.get().id())
                : e.isEmpty() ? Optional.empty() : users.findFirstByEmailIgnoreCaseOrderByIdAsc(e);
        user.filter(u -> !profiles.isEmailVerified(u)).ifPresent(this::sendVerification);
        return Map.of("detail", VERIFICATION_RESENT_MSG);
    }

    public boolean sendVerification(UserAccount user) {
        return emails.verification(ProfileService.recipient(user), links.emailVerificationUrl(user), links.mobileVerifyUrl(user));
    }

    // ------------------------------------------------------------------ password reset

    /** PasswordResetRequestView: always the same answer, email sent only when possible. */
    public Map<String, Object> requestPasswordReset(Map<String, Object> body) {
        RequestData d = RequestData.of(body);
        String identifier = d.string("identifier", Field.required().maxLength(254));
        d.validate();
        findUserByIdentifier(identifier).ifPresent(this::sendPasswordReset);
        return Map.of("detail", PASSWORD_RESET_SENT_MSG);
    }

    private Optional<UserAccount> findUserByIdentifier(String identifier) {
        String ident = identifier == null ? "" : identifier.strip();
        if (ident.isEmpty()) {
            return Optional.empty();
        }
        if (ident.contains("@")) {
            return users.findFirstByEmailIgnoreCaseOrderByIdAsc(ident);
        }
        Optional<UserAccount> byName = users.findFirstByUsernameIgnoreCaseOrderByIdAsc(ident);
        return byName.isPresent() ? byName : users.findFirstByEmailIgnoreCaseOrderByIdAsc(ident);
    }

    private boolean sendPasswordReset(UserAccount user) {
        if (user.getEmail() == null || user.getEmail().strip().isEmpty()) {
            log.info("Password reset skipped: user {} has no email.", user.getId());
            return false;
        }
        if (!user.hasUsablePassword()) {
            log.info("Password reset skipped: user {} has no local password.", user.getId());
            return false;
        }
        String uid = AuthLinks.uidFor(user);
        String token = passwordResetTokens.makeToken(user);
        String resetUrl = links.passwordResetOpenUrl(uid, token);
        String appUrl = links.mobileDeepLink("reset-password", "uid", uid, "token", token);
        return emails.passwordReset(ProfileService.recipient(user), resetUrl, appUrl);
    }

    /** GET /auth/password-reset/open/. */
    public String passwordResetOpenPage(String uid, String token) {
        return AuthLinks.handoffHtml("Reset your password", "Opening Finance Tracker to choose a new password.",
                links.mobileDeepLink("reset-password", "uid", uid, "token", token),
                props.getFrontendUrl() + "/reset-password?uid=" + uid + "&token=" + token);
    }

    /** PasswordResetConfirmView. */
    @Transactional
    public Map<String, Object> confirmPasswordReset(Map<String, Object> body) {
        RequestData d = RequestData.of(body);
        String uid = d.string("uid", Field.required());
        String token = d.string("token", Field.required());
        String password = validatedPassword(d, "password");
        String confirm = d.string("password_confirm", Field.required());
        d.validate();
        if (!password.equals(confirm)) {
            throw ApiException.field("password_confirm", "Passwords do not match.");
        }
        Optional<UserAccount> user = decodeUid(uid).flatMap(users::findById);
        if (user.isEmpty() || !passwordResetTokens.checkToken(user.get(), token)) {
            throw ApiException.badRequest(INVALID_RESET);
        }
        UserAccount u = user.get();
        u.setPassword(hasher.encode(password));
        users.save(u);
        return Map.of("detail", "Password updated. You can sign in with your new password.");
    }

    // ------------------------------------------------------------------ Firebase

    /** FirebaseLoginView: verify a Firebase ID token, then issue this API's JWTs. */
    @Transactional
    public Map<String, Object> firebaseLogin(Map<String, Object> body) {
        RequestData d = RequestData.of(body);
        String token = d.string("id_token", Field.required());
        d.validate();
        if (token.startsWith("Bearer ")) {
            token = token.split(" ", 2)[1];
        }
        FirebaseToken decoded;
        try {
            FirebaseApp app = firebase.app().orElseThrow(() -> new IllegalStateException("Firebase not configured"));
            decoded = FirebaseAuth.getInstance(app).verifyIdToken(token);
        } catch (Exception e) {
            throw ApiException.detail(HttpStatus.UNAUTHORIZED, "Invalid Firebase token.");
        }
        String uid = decoded.getUid();
        String email = decoded.getEmail() == null ? "" : decoded.getEmail();
        Object displayName = decoded.getClaims().get("displayName");
        String name = decoded.getName() != null && !decoded.getName().isEmpty() ? decoded.getName()
                : displayName != null ? String.valueOf(displayName) : "";
        boolean emailVerifiedFb = decoded.isEmailVerified();
        syncFirestoreUser(uid, email, name, decoded.getPicture(), emailVerifiedFb);

        Optional<UserAccount> existing = users.findByUsername(uid);
        boolean created = existing.isEmpty();
        UserAccount user = existing.orElseGet(() -> {
            UserAccount u = new UserAccount();
            u.setUsername(uid);
            u.setEmail(email);
            u.setFirstName(name);
            u.setDateJoined(Instant.now(clock));
            return users.save(u);
        });
        if (!created && !email.isEmpty() && !email.equals(user.getEmail())) {
            user.setEmail(email);
            users.save(user);
        }
        profiles.profile(user);
        if (emailVerifiedFb) {
            profiles.markEmailVerified(user);
        } else if (created) {
            profiles.setEmailVerifiedFlag(user, false);
        }
        SimpleJwtTokens.Pair tokens = jwt.forUser(user);
        Map<String, Object> out = new LinkedHashMap<>();
        out.put("user", profiles.profileJson(user));
        out.put("refresh", tokens.refresh());
        out.put("access", tokens.access());
        return out;
    }

    /** Firestore "users" mirror kept by the Django view (only when Firestore is the data store). */
    private void syncFirestoreUser(String uid, String email, String name, String photo, boolean emailVerified) {
        Firestore db = firestore.getIfAvailable();
        if (db == null) {
            return;
        }
        try {
            DocumentReference ref = db.collection("users").document(uid);
            Map<String, Object> payload = new LinkedHashMap<>();
            payload.put("uid", uid);
            payload.put("email", email);
            payload.put("name", name);
            payload.put("photo", photo);
            payload.put("email_verified", emailVerified);
            if (!ref.get().get().exists()) {
                payload.put("created_at", FieldValue.serverTimestamp());
                payload.put("last_login", FieldValue.serverTimestamp());
                ref.set(payload).get();
            } else {
                payload.put("last_login", FieldValue.serverTimestamp());
                ref.update(payload).get();
            }
        } catch (Exception e) {
            log.warn("Firestore user sync failed for uid {}", uid, e);
        }
    }

    // ------------------------------------------------------------------ helpers

    /** decode_uid: url-safe base64 (padding restored) to a numeric primary key. */
    static Optional<Long> decodeUid(String uidB64) {
        try {
            String value = uidB64 == null ? "" : uidB64.strip();
            if (value.isEmpty()) {
                return Optional.empty();
            }
            return parseId(Py.urlsafeB64Decode(value));
        } catch (IllegalArgumentException e) {
            return Optional.empty();
        }
    }

    static Optional<Long> parseId(String s) {
        try {
            return Optional.of(Long.parseLong(s.strip()));
        } catch (NumberFormatException e) {
            return Optional.empty();
        }
    }

    public Optional<UserAccount> user(AuthUser principal) {
        return users.findById(principal.id());
    }
}
