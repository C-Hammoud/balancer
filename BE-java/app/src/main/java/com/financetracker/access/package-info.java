/**
 * Access manager: registration, login (simplejwt-compatible JWTs), email verification, password
 * reset, Firebase login, profile and locale preferences. Other modules may only use
 * {@code access.api}.
 */
@ApplicationModule(displayName = "Access manager")
package com.financetracker.access;

import org.springframework.modulith.ApplicationModule;
