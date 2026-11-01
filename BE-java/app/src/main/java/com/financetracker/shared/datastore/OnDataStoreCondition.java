package com.financetracker.shared.datastore;

import java.util.Map;

import org.springframework.context.annotation.Condition;
import org.springframework.context.annotation.ConditionContext;
import org.springframework.core.type.AnnotatedTypeMetadata;

import com.financetracker.shared.config.DataStoreType;

class OnDataStoreCondition implements Condition {

    @Override
    public boolean matches(ConditionContext context, AnnotatedTypeMetadata metadata) {
        Map<String, Object> attrs = metadata.getAnnotationAttributes(ConditionalOnDataStore.class.getName());
        if (attrs == null) {
            return true;
        }
        DataStoreType wanted = (DataStoreType) attrs.get("value");
        DataStoreType selected = DataStoreType.parse(context.getEnvironment().getProperty("app.datastore", "jpa"));
        return wanted == selected;
    }
}
