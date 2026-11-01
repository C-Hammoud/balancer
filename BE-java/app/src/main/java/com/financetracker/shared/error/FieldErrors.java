package com.financetracker.shared.error;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;

/** Collects DRF serializer errors ({"field": ["msg", ...]}) in field order. */
public final class FieldErrors {

    private final Map<String, List<String>> errors = new LinkedHashMap<>();

    public FieldErrors add(String field, String message) {
        errors.computeIfAbsent(field, k -> new ArrayList<>()).add(message);
        return this;
    }

    public FieldErrors addAll(String field, List<String> messages) {
        for (String m : messages) {
            add(field, m);
        }
        return this;
    }

    public boolean has(String field) {
        return errors.containsKey(field);
    }

    public boolean isEmpty() {
        return errors.isEmpty();
    }

    public Map<String, Object> toBody() {
        return new LinkedHashMap<>(errors);
    }

    public void throwIfAny() {
        if (!errors.isEmpty()) {
            throw new ApiException(HttpStatus.BAD_REQUEST, toBody());
        }
    }
}
