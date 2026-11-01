package com.financetracker.shared.web;

import java.time.Clock;
import java.util.List;

import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

import com.financetracker.shared.config.AppProperties;

@Configuration(proxyBeanMethods = false)
class WebConfiguration {

    @Bean
    @ConditionalOnMissingBean
    Clock clock() {
        return Clock.systemDefaultZone();
    }

    /**
     * django-cors-headers settings: debug allows every origin without credentials; otherwise only
     * CORS_ALLOWED_ORIGINS, with credentials.
     */
    @Bean
    CorsConfigurationSource corsConfigurationSource(AppProperties props) {
        CorsConfiguration cors = new CorsConfiguration();
        if (props.isDebug()) {
            cors.setAllowedOriginPatterns(List.of("*"));
            cors.setAllowCredentials(false);
        } else {
            cors.setAllowedOrigins(props.getCorsAllowedOrigins().stream().map(String::strip)
                    .filter(s -> !s.isEmpty()).toList());
            cors.setAllowCredentials(true);
        }
        cors.setAllowedMethods(List.of("DELETE", "GET", "OPTIONS", "PATCH", "POST", "PUT"));
        cors.setAllowedHeaders(List.of("accept", "accept-encoding", "authorization", "content-type", "dnt",
                "origin", "user-agent", "x-csrftoken", "x-requested-with"));
        cors.setMaxAge(86400L);
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/**", cors);
        return source;
    }
}
