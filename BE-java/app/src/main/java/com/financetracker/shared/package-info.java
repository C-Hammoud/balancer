/**
 * Cross-cutting building blocks used by every module: configuration, DRF-compatible errors,
 * request parsing, locale/currency helpers, the authenticated principal and data-store wiring.
 * Open module: all of its packages may be used by other modules.
 */
@ApplicationModule(type = ApplicationModule.Type.OPEN)
package com.financetracker.shared;

import org.springframework.modulith.ApplicationModule;
