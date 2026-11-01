package com.financetracker;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.scheduling.annotation.EnableScheduling;

/**
 * Modular monolith: {@code shared}, {@code access}, {@code notifications} and {@code finance}
 * are Spring Modulith application modules (one top-level package each).
 */
@SpringBootApplication
@ConfigurationPropertiesScan
@EnableScheduling
public class FinanceTrackerApplication {

    public static void main(String[] args) {
        SpringApplication.run(FinanceTrackerApplication.class, args);
    }
}
