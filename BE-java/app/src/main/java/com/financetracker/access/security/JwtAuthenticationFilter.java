package com.financetracker.access.security;

import java.io.IOException;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

import com.financetracker.access.domain.AccessRepositories.UserAccountRepository;
import com.financetracker.access.domain.UserAccount;
import com.financetracker.shared.security.AuthUser;
import com.financetracker.shared.web.JsonResponses;

/**
 * simplejwt JWTAuthentication: "Authorization: Bearer <access>" populates the security context.
 * A malformed or invalid token is a 401 on every endpoint that has authentication enabled, even
 * AllowAny ones (as in DRF); endpoints declared with authentication_classes = () skip it.
 */
public class JwtAuthenticationFilter extends OncePerRequestFilter {

    /** Views with authentication_classes = () in the Django code. */
    static final Set<String> NO_AUTHENTICATION_PATHS = Set.of(
            "/healthz/",
            "/api/v1/health/",
            "/api/v1/auth/logout/",
            "/api/v1/auth/email-verify/confirm/",
            "/api/v1/auth/password-reset/open/");

    private static final Map<String, String> CHALLENGE = Map.of("WWW-Authenticate", "Bearer realm=\"api\"");

    private final SimpleJwtTokens tokens;
    private final UserAccountRepository users;

    public JwtAuthenticationFilter(SimpleJwtTokens tokens, UserAccountRepository users) {
        this.tokens = tokens;
        this.users = users;
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response, FilterChain chain)
            throws ServletException, IOException {
        if (NO_AUTHENTICATION_PATHS.contains(request.getRequestURI())) {
            chain.doFilter(request, response);
            return;
        }
        String header = request.getHeader("Authorization");
        String[] parts = header == null ? new String[0] : header.strip().split("\\s+");
        if (parts.length == 0 || parts[0].isEmpty() || !"Bearer".equals(parts[0])) {
            chain.doFilter(request, response);
            return;
        }
        if (parts.length != 2) {
            fail(response, body("Authorization header must contain two space-delimited values", "bad_authorization_header"));
            return;
        }

        Map<String, Object> payload;
        try {
            payload = tokens.validateAccess(parts[1]);
        } catch (TokenError e) {
            Map<String, Object> message = new LinkedHashMap<>();
            message.put("token_class", "AccessToken");
            message.put("token_type", "access");
            message.put("message", e.getMessage());
            Map<String, Object> b = body("Given token not valid for any token type", "token_not_valid");
            b.put("messages", List.of(message));
            fail(response, b);
            return;
        }

        Object userIdClaim = payload.get("user_id");
        if (userIdClaim == null) {
            fail(response, body("Token contained no recognizable user identification", "token_not_valid"));
            return;
        }
        Optional<UserAccount> user = parseId(userIdClaim).flatMap(users::findById);
        if (user.isEmpty()) {
            fail(response, body("User not found", "user_not_found"));
            return;
        }
        if (!user.get().isActive()) {
            fail(response, body("User is inactive", "user_inactive"));
            return;
        }
        UserAccount u = user.get();
        AuthUser principal = new AuthUser(u.getId(), u.getUsername(), u.isStaff());
        List<SimpleGrantedAuthority> authorities = u.isStaff()
                ? List.of(new SimpleGrantedAuthority("ROLE_USER"), new SimpleGrantedAuthority("ROLE_STAFF"))
                : List.of(new SimpleGrantedAuthority("ROLE_USER"));
        SecurityContextHolder.getContext().setAuthentication(
                UsernamePasswordAuthenticationToken.authenticated(principal, null, authorities));
        chain.doFilter(request, response);
    }

    private static Optional<Long> parseId(Object claim) {
        try {
            return Optional.of(Long.valueOf(String.valueOf(claim)));
        } catch (NumberFormatException e) {
            return Optional.empty();
        }
    }

    private static Map<String, Object> body(String detail, String code) {
        Map<String, Object> b = new LinkedHashMap<>();
        b.put("detail", detail);
        b.put("code", code);
        return b;
    }

    private static void fail(HttpServletResponse response, Map<String, Object> body) throws IOException {
        JsonResponses.write(response, HttpServletResponse.SC_UNAUTHORIZED, body, CHALLENGE);
    }
}
