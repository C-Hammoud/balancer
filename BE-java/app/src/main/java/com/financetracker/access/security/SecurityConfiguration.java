package com.financetracker.access.security;

import java.time.Clock;
import java.util.Map;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.authentication.AnonymousAuthenticationFilter;

import com.financetracker.access.domain.AccessRepositories.UserAccountRepository;
import com.financetracker.shared.config.AppProperties;
import com.financetracker.shared.error.ApiException;
import com.financetracker.shared.web.JsonResponses;

/**
 * DRF defaults: JWT authentication, IsAuthenticated everywhere except the AllowAny views.
 * Stateless; no sessions, CSRF or form login.
 */
@Configuration(proxyBeanMethods = false)
class SecurityConfiguration {

    /** Views with permission_classes = (AllowAny,) (or empty) in the Django code. */
    static final String[] PUBLIC_PATHS = {
            "/healthz/",
            "/api/v1/health/",
            "/api/v1/auth/register/",
            "/api/v1/auth/login/",
            "/api/v1/auth/email-verify/confirm/",
            "/api/v1/auth/email-verify/resend/",
            "/api/v1/auth/password-reset/",
            "/api/v1/auth/password-reset/open/",
            "/api/v1/auth/password-reset/confirm/",
            "/api/v1/auth/token/refresh/",
            "/api/v1/auth/logout/",
            "/api/v1/auth/firebase/",
            "/actuator/health",
            "/actuator/health/**",
            "/error",
    };

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http, SimpleJwtTokens tokens, UserAccountRepository users)
            throws Exception {
        Map<String, String> challenge = Map.of("WWW-Authenticate", "Bearer realm=\"api\"");
        http
                .csrf(AbstractHttpConfigurer::disable)
                .cors(Customizer.withDefaults())
                .httpBasic(AbstractHttpConfigurer::disable)
                .formLogin(AbstractHttpConfigurer::disable)
                .logout(AbstractHttpConfigurer::disable)
                .requestCache(AbstractHttpConfigurer::disable)
                .sessionManagement(s -> s.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .addFilterBefore(new JwtAuthenticationFilter(tokens, users), AnonymousAuthenticationFilter.class)
                .exceptionHandling(e -> e
                        .authenticationEntryPoint((request, response, ex) -> JsonResponses.write(response, 401,
                                ApiException.detailBody("Authentication credentials were not provided."), challenge))
                        .accessDeniedHandler((request, response, ex) -> JsonResponses.write(response, 403,
                                ApiException.detailBody("You do not have permission to perform this action."), Map.of())))
                .authorizeHttpRequests(a -> a
                        .requestMatchers(HttpMethod.OPTIONS, "/**").permitAll()
                        .requestMatchers(PUBLIC_PATHS).permitAll()
                        .anyRequest().authenticated());
        return http.build();
    }

    /** No form/basic users: replaces Spring Boot's generated in-memory user. */
    @Bean
    UserDetailsService noUserDetails() {
        return username -> {
            throw new UsernameNotFoundException(username);
        };
    }

    @Bean
    DjangoTokenGenerator passwordResetTokens(AppProperties props, Clock clock) {
        return new DjangoTokenGenerator(DjangoTokenGenerator.PASSWORD_RESET_SALT, props.getSecretKey(),
                props.getPasswordResetTimeout(), clock);
    }

    @Bean
    DjangoTokenGenerator emailVerificationTokens(AppProperties props, Clock clock) {
        return new DjangoTokenGenerator(DjangoTokenGenerator.EMAIL_VERIFICATION_SALT, props.getSecretKey(),
                props.getPasswordResetTimeout(), clock);
    }
}
