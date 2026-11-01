package com.financetracker.shared.datastore;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.boot.EnvironmentPostProcessor;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.config.ConfigDataEnvironmentPostProcessor;
import org.springframework.core.Ordered;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.core.env.MapPropertySource;

import com.financetracker.shared.config.DataStoreType;

/**
 * With app.datastore=firestore there is no relational database: switch off the JDBC/JPA/Flyway
 * auto-configuration so the app starts without a datasource. Runs after application.yml and
 * .env are loaded, so DATA_STORE from either place is honoured.
 */
public class DataStoreEnvironmentPostProcessor implements EnvironmentPostProcessor, Ordered {

    static final List<String> SQL_AUTO_CONFIGURATIONS = List.of(
            "org.springframework.boot.jdbc.autoconfigure.DataSourceAutoConfiguration",
            "org.springframework.boot.jdbc.autoconfigure.DataSourceInitializationAutoConfiguration",
            "org.springframework.boot.jdbc.autoconfigure.DataSourceTransactionManagerAutoConfiguration",
            "org.springframework.boot.jdbc.autoconfigure.JdbcClientAutoConfiguration",
            "org.springframework.boot.jdbc.autoconfigure.JdbcTemplateAutoConfiguration",
            "org.springframework.boot.jdbc.autoconfigure.health.DataSourceHealthContributorAutoConfiguration",
            "org.springframework.boot.jdbc.autoconfigure.metrics.DataSourcePoolMetricsAutoConfiguration",
            "org.springframework.boot.hibernate.autoconfigure.HibernateJpaAutoConfiguration",
            "org.springframework.boot.hibernate.autoconfigure.metrics.HibernateMetricsAutoConfiguration",
            "org.springframework.boot.flyway.autoconfigure.FlywayAutoConfiguration",
            "org.springframework.boot.flyway.autoconfigure.FlywayEndpointAutoConfiguration",
            "org.springframework.boot.data.jpa.autoconfigure.DataJpaRepositoriesAutoConfiguration");

    @Override
    public void postProcessEnvironment(ConfigurableEnvironment environment, SpringApplication application) {
        DataStoreType type = DataStoreType.parse(environment.getProperty("app.datastore", "jpa"));
        if (type != DataStoreType.FIRESTORE) {
            return;
        }
        List<String> excludes = new ArrayList<>(SQL_AUTO_CONFIGURATIONS);
        String existing = environment.getProperty("spring.autoconfigure.exclude", "");
        for (String e : existing.split(",")) {
            if (!e.isBlank()) {
                excludes.add(e.trim());
            }
        }
        Map<String, Object> props = new LinkedHashMap<>();
        props.put("spring.autoconfigure.exclude", String.join(",", excludes));
        environment.getPropertySources().addFirst(new MapPropertySource("firestoreDataStore", props));
    }

    @Override
    public int getOrder() {
        return ConfigDataEnvironmentPostProcessor.ORDER + 1;
    }
}
