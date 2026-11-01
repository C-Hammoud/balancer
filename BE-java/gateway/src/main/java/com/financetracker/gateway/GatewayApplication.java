package com.financetracker.gateway;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

/**
 * Portal balancer: the single public entry point. Routes each API area (access, finance,
 * notifications) to the backend that serves it, so areas can move between Django, the Java
 * modular monolith and, later, separate services without the Angular or Expo clients changing.
 */
@SpringBootApplication
public class GatewayApplication {

    public static void main(String[] args) {
        SpringApplication.run(GatewayApplication.class, args);
    }
}
