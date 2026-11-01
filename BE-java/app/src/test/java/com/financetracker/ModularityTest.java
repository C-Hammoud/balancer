package com.financetracker;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

/** Fails the build when a module uses another module's internals or modules form a cycle. */
class ModularityTest {

    @Test
    void moduleBoundariesAreRespected() {
        ApplicationModules.of(FinanceTrackerApplication.class).verify();
    }
}
