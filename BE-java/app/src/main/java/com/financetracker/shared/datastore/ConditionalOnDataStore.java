package com.financetracker.shared.datastore;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.context.annotation.Conditional;

import com.financetracker.shared.config.DataStoreType;

/**
 * Activates a bean or configuration only for the selected {@code app.datastore}. Every repository
 * adapter is annotated with this, so exactly one implementation of each repository port exists.
 */
@Target({ElementType.TYPE, ElementType.METHOD})
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Conditional(OnDataStoreCondition.class)
public @interface ConditionalOnDataStore {

    DataStoreType value();
}
