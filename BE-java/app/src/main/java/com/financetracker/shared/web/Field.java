package com.financetracker.shared.web;

import java.math.BigDecimal;

/**
 * Declares how one request field is validated, mirroring a DRF serializer field's options
 * (required / default / allow_blank / allow_null / max_length / min_value / max_digits ...).
 */
public final class Field {

    boolean required = true;
    boolean hasDefault;
    Object defaultValue;
    boolean allowBlank;
    boolean allowNull;
    boolean trim = true;
    Integer maxLength;
    Integer minLength;
    BigDecimal minValue;
    BigDecimal maxValue;
    Integer maxDigits;
    Integer decimalPlaces;
    boolean allowEmpty = true;

    private Field() {
    }

    /** required=True (DRF default). */
    public static Field required() {
        return new Field();
    }

    /** required=False, no default: omitted from validated data when absent. */
    public static Field optional() {
        Field f = new Field();
        f.required = false;
        return f;
    }

    /** required=False with default. */
    public static Field withDefault(Object value) {
        Field f = new Field();
        f.required = false;
        f.hasDefault = true;
        f.defaultValue = value;
        return f;
    }

    public Field allowBlank() {
        this.allowBlank = true;
        return this;
    }

    public Field allowNull() {
        this.allowNull = true;
        return this;
    }

    public Field noTrim() {
        this.trim = false;
        return this;
    }

    public Field maxLength(int n) {
        this.maxLength = n;
        return this;
    }

    public Field minLength(int n) {
        this.minLength = n;
        return this;
    }

    public Field min(long v) {
        this.minValue = BigDecimal.valueOf(v);
        return this;
    }

    public Field max(long v) {
        this.maxValue = BigDecimal.valueOf(v);
        return this;
    }

    public Field digits(int maxDigits, int decimalPlaces) {
        this.maxDigits = maxDigits;
        this.decimalPlaces = decimalPlaces;
        return this;
    }

    /** ListField(allow_empty=False). */
    public Field nonEmpty() {
        this.allowEmpty = false;
        return this;
    }
}
