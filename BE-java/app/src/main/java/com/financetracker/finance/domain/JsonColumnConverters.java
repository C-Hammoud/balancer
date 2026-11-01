package com.financetracker.finance.domain;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;

import tools.jackson.core.type.TypeReference;
import tools.jackson.databind.json.JsonMapper;

/** JSON text columns for the plan's lines and warnings (Django JSONField). */
public final class JsonColumnConverters {

    private static final JsonMapper JSON = JsonMapper.builder().build();

    private JsonColumnConverters() {
    }

    @Converter
    public static class MapList implements AttributeConverter<List<Map<String, Object>>, String> {

        @Override
        public String convertToDatabaseColumn(List<Map<String, Object>> value) {
            return JSON.writeValueAsString(value == null ? List.of() : value);
        }

        @Override
        public List<Map<String, Object>> convertToEntityAttribute(String db) {
            if (db == null || db.isBlank()) {
                return new ArrayList<>();
            }
            return JSON.readValue(db, new TypeReference<List<Map<String, Object>>>() { });
        }
    }

    @Converter
    public static class StringList implements AttributeConverter<List<String>, String> {

        @Override
        public String convertToDatabaseColumn(List<String> value) {
            return JSON.writeValueAsString(value == null ? List.of() : value);
        }

        @Override
        public List<String> convertToEntityAttribute(String db) {
            if (db == null || db.isBlank()) {
                return new ArrayList<>();
            }
            return JSON.readValue(db, new TypeReference<List<String>>() { });
        }
    }
}
