package com.financetracker.shared.web;

import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;
import java.time.DateTimeException;
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import com.financetracker.shared.error.FieldErrors;

/**
 * Reads a JSON request body field by field with the same rules and error messages as the DRF
 * serializer fields the Django views used. Errors accumulate; call {@link #validate()} to throw a
 * 400 with {"field": ["message"]}.
 */
public final class RequestData {

    public static final String REQUIRED = "This field is required.";
    public static final String NULL = "This field may not be null.";
    public static final String BLANK = "This field may not be blank.";

    private static final Set<Object> TRUE_VALUES = Set.of("t", "T", "y", "Y", "yes", "Yes", "YES",
            "true", "True", "TRUE", "on", "On", "ON", "1");
    private static final Set<Object> FALSE_VALUES = Set.of("f", "F", "n", "N", "no", "No", "NO",
            "false", "False", "FALSE", "off", "Off", "OFF", "0");
    private static final Pattern DATE_RE = Pattern.compile("(\\d{4})-(\\d{1,2})-(\\d{1,2})");
    private static final Pattern TRAILING_DECIMAL_ZERO = Pattern.compile("\\.0*\\s*$");

    private final Map<String, Object> data;
    private final boolean partial;
    private final FieldErrors errors = new FieldErrors();
    private final Map<String, Object> validated = new LinkedHashMap<>();

    private RequestData(Map<String, Object> data, boolean partial) {
        this.data = data == null ? Collections.emptyMap() : data;
        this.partial = partial;
    }

    public static RequestData of(Map<String, Object> body) {
        return new RequestData(body, false);
    }

    /** PATCH semantics: absent fields are skipped, defaults are not applied. */
    public static RequestData partial(Map<String, Object> body) {
        return new RequestData(body, true);
    }

    public Map<String, Object> raw() {
        return data;
    }

    public boolean has(String key) {
        return data.containsKey(key);
    }

    public Object rawValue(String key) {
        return data.get(key);
    }

    /** True when the key ended up in validated data (supplied, or filled from a default). */
    public boolean provided(String key) {
        return validated.containsKey(key);
    }

    public Map<String, Object> validated() {
        return validated;
    }

    public FieldErrors errors() {
        return errors;
    }

    public boolean hasErrors() {
        return !errors.isEmpty();
    }

    public void validate() {
        errors.throwIfAny();
    }

    // ---------------------------------------------------------------- CharField / EmailField

    public String string(String key, Field f) {
        if (!data.containsKey(key)) {
            return absent(key, f);
        }
        Object v = data.get(key);
        if (v == null) {
            return nullValue(key, f);
        }
        if (v instanceof Boolean || !(v instanceof String || v instanceof Number)) {
            errors.add(key, "Not a valid string.");
            return null;
        }
        String s = pyStr(v);
        if (s.isEmpty() || (f.trim && s.strip().isEmpty())) {
            if (!f.allowBlank) {
                errors.add(key, BLANK);
                return null;
            }
            return ok(key, "");
        }
        if (f.trim) {
            s = s.strip();
        }
        List<String> problems = new ArrayList<>();
        if (f.maxLength != null && s.codePointCount(0, s.length()) > f.maxLength) {
            problems.add("Ensure this field has no more than " + f.maxLength + " characters.");
        }
        if (f.minLength != null && s.codePointCount(0, s.length()) < f.minLength) {
            problems.add("Ensure this field has at least " + f.minLength + " characters.");
        }
        if (!problems.isEmpty()) {
            errors.addAll(key, problems);
            return null;
        }
        return ok(key, s);
    }

    public String email(String key, Field f) {
        String s = string(key, f);
        if (s == null || s.isEmpty() || errors.has(key)) {
            return s;
        }
        if (!EmailValidator.isValid(s)) {
            errors.add(key, "Enter a valid email address.");
            validated.remove(key);
            return null;
        }
        return s;
    }

    // ---------------------------------------------------------------- ChoiceField

    public String choice(String key, Collection<String> choices, Field f) {
        if (!data.containsKey(key)) {
            return absent(key, f);
        }
        Object v = data.get(key);
        if (v == null) {
            return nullValue(key, f);
        }
        if ("".equals(v) && f.allowBlank) {
            return ok(key, "");
        }
        String s = pyStr(v);
        if (!choices.contains(s)) {
            errors.add(key, "\"" + s + "\" is not a valid choice.");
            return null;
        }
        return ok(key, s);
    }

    // ---------------------------------------------------------------- BooleanField

    public Boolean bool(String key, Field f) {
        if (!data.containsKey(key)) {
            return absent(key, f);
        }
        Object v = data.get(key);
        if (v == null || (f.allowNull && "null".equalsIgnoreCase(String.valueOf(v))) || (f.allowNull && "".equals(v))) {
            return nullValue(key, f);
        }
        Boolean b = parseBool(v);
        if (b == null) {
            errors.add(key, "Must be a valid boolean.");
            return null;
        }
        return ok(key, b);
    }

    /** DRF BooleanField truthiness; null when the value is not a recognised boolean. */
    public static Boolean parseBool(Object v) {
        if (v instanceof Boolean b) {
            return b;
        }
        if (v instanceof Number n) {
            double d = n.doubleValue();
            if (d == 1d) {
                return Boolean.TRUE;
            }
            if (d == 0d) {
                return Boolean.FALSE;
            }
            return null;
        }
        if (TRUE_VALUES.contains(v)) {
            return Boolean.TRUE;
        }
        if (FALSE_VALUES.contains(v)) {
            return Boolean.FALSE;
        }
        return null;
    }

    // ---------------------------------------------------------------- IntegerField

    public Integer integer(String key, Field f) {
        if (!data.containsKey(key)) {
            return absent(key, f);
        }
        Object v = data.get(key);
        if (v == null) {
            return nullValue(key, f);
        }
        Integer parsed = parseInt(v);
        if (parsed == null) {
            errors.add(key, "A valid integer is required.");
            return null;
        }
        List<String> problems = new ArrayList<>();
        if (f.maxValue != null && BigDecimal.valueOf(parsed).compareTo(f.maxValue) > 0) {
            problems.add("Ensure this value is less than or equal to " + f.maxValue.toPlainString() + ".");
        }
        if (f.minValue != null && BigDecimal.valueOf(parsed).compareTo(f.minValue) < 0) {
            problems.add("Ensure this value is greater than or equal to " + f.minValue.toPlainString() + ".");
        }
        if (!problems.isEmpty()) {
            errors.addAll(key, problems);
            return null;
        }
        return ok(key, parsed);
    }

    /** DRF IntegerField parsing: int(re.sub(r'\.0*\s*$', '', str(data))). */
    public static Integer parseInt(Object v) {
        if (v instanceof Boolean) {
            return null;
        }
        String s = pyStr(v);
        if (s.length() > 1000) {
            return null;
        }
        s = TRAILING_DECIMAL_ZERO.matcher(s).replaceFirst("");
        try {
            return Integer.parseInt(s.strip().replace("_", ""));
        } catch (NumberFormatException e) {
            return null;
        }
    }

    // ---------------------------------------------------------------- DecimalField

    public BigDecimal decimal(String key, Field f) {
        if (!data.containsKey(key)) {
            Object d = absent(key, f);
            if (d == null) {
                return null;
            }
            BigDecimal dv = d instanceof BigDecimal bd ? bd : new BigDecimal(pyStr(d));
            validated.put(key, dv);
            return dv;
        }
        Object v = data.get(key);
        if (v == null) {
            return nullValue(key, f);
        }
        if (v instanceof Boolean) {
            errors.add(key, "A valid number is required.");
            return null;
        }
        String s = pyStr(v).strip();
        if (s.length() > 1000) {
            errors.add(key, "String value too large.");
            return null;
        }
        BigDecimal value;
        try {
            value = new BigDecimal(s);
        } catch (NumberFormatException e) {
            errors.add(key, "A valid number is required.");
            return null;
        }
        String precision = precisionError(value, f);
        if (precision != null) {
            errors.add(key, precision);
            return null;
        }
        if (f.decimalPlaces != null) {
            MathContext mc = new MathContext(f.maxDigits != null ? f.maxDigits : 28, RoundingMode.HALF_EVEN);
            value = value.setScale(f.decimalPlaces, RoundingMode.HALF_EVEN).round(mc);
        }
        List<String> problems = new ArrayList<>();
        if (f.maxValue != null && value.compareTo(f.maxValue) > 0) {
            problems.add("Ensure this value is less than or equal to " + f.maxValue.toPlainString() + ".");
        }
        if (f.minValue != null && value.compareTo(f.minValue) < 0) {
            problems.add("Ensure this value is greater than or equal to " + f.minValue.toPlainString() + ".");
        }
        if (!problems.isEmpty()) {
            errors.addAll(key, problems);
            return null;
        }
        return ok(key, value);
    }

    /** DRF DecimalField.validate_precision. */
    private static String precisionError(BigDecimal value, Field f) {
        if (f.maxDigits == null && f.decimalPlaces == null) {
            return null;
        }
        int digits = value.unscaledValue().abs().toString().length();
        int exponent = -value.scale();
        int totalDigits;
        int wholeDigits;
        int places;
        if (exponent >= 0) {
            totalDigits = digits + exponent;
            wholeDigits = totalDigits;
            places = 0;
        } else if (digits > Math.abs(exponent)) {
            totalDigits = digits;
            wholeDigits = totalDigits - Math.abs(exponent);
            places = Math.abs(exponent);
        } else {
            totalDigits = Math.abs(exponent);
            wholeDigits = 0;
            places = totalDigits;
        }
        if (f.maxDigits != null && totalDigits > f.maxDigits) {
            return "Ensure that there are no more than " + f.maxDigits + " digits in total.";
        }
        if (f.decimalPlaces != null && places > f.decimalPlaces) {
            return "Ensure that there are no more than " + f.decimalPlaces + " decimal places.";
        }
        if (f.maxDigits != null && f.decimalPlaces != null && wholeDigits > f.maxDigits - f.decimalPlaces) {
            return "Ensure that there are no more than " + (f.maxDigits - f.decimalPlaces)
                    + " digits before the decimal point.";
        }
        return null;
    }

    // ---------------------------------------------------------------- DateField

    public LocalDate date(String key, Field f) {
        if (!data.containsKey(key)) {
            Object d = absent(key, f);
            return d instanceof LocalDate ld ? ld : null;
        }
        Object v = data.get(key);
        if (v == null) {
            return nullValue(key, f);
        }
        LocalDate parsed = v instanceof String s ? parseDate(s) : null;
        if (parsed == null) {
            errors.add(key, "Date has wrong format. Use one of these formats instead: YYYY-MM-DD.");
            return null;
        }
        return ok(key, parsed);
    }

    /** django.utils.dateparse.parse_date: ISO date, or YYYY-M-D. */
    public static LocalDate parseDate(String s) {
        if (s == null) {
            return null;
        }
        try {
            return LocalDate.parse(s);
        } catch (DateTimeException e) {
            Matcher m = DATE_RE.matcher(s);
            if (m.matches()) {
                try {
                    return LocalDate.of(Integer.parseInt(m.group(1)), Integer.parseInt(m.group(2)),
                            Integer.parseInt(m.group(3)));
                } catch (DateTimeException ignored) {
                    return null;
                }
            }
            return null;
        }
    }

    // ---------------------------------------------------------------- ListField(child=CharField())

    @SuppressWarnings("unchecked")
    public List<String> stringList(String key, Field f) {
        if (!data.containsKey(key)) {
            Object d = absent(key, f);
            return d instanceof List<?> l ? (List<String>) l : null;
        }
        Object v = data.get(key);
        if (v == null) {
            return nullValue(key, f);
        }
        if (!(v instanceof List<?> list)) {
            String type = v instanceof String ? "str" : v instanceof Map ? "dict" : v.getClass().getSimpleName();
            errors.add(key, "Expected a list of items but got type \"" + type + "\".");
            return null;
        }
        if (!f.allowEmpty && list.isEmpty()) {
            errors.add(key, "This list may not be empty.");
            return null;
        }
        List<String> out = new ArrayList<>();
        for (Object item : list) {
            if (item == null || item instanceof Boolean || !(item instanceof String || item instanceof Number)) {
                errors.add(key, "Not a valid string.");
                return null;
            }
            String s = pyStr(item).strip();
            if (s.isEmpty()) {
                errors.add(key, BLANK);
                return null;
            }
            out.add(s);
        }
        return ok(key, out);
    }

    // ---------------------------------------------------------------- helpers

    @SuppressWarnings("unchecked")
    private <T> T absent(String key, Field f) {
        if (partial) {
            return null;
        }
        if (f.required) {
            errors.add(key, REQUIRED);
            return null;
        }
        if (f.hasDefault) {
            validated.put(key, f.defaultValue);
            return (T) f.defaultValue;
        }
        return null;
    }

    private <T> T nullValue(String key, Field f) {
        if (f.allowNull) {
            validated.put(key, null);
            return null;
        }
        errors.add(key, NULL);
        return null;
    }

    private <T> T ok(String key, T value) {
        validated.put(key, value);
        return value;
    }

    /** Python str() of a JSON scalar (1.0 stays "1.0", integers have no fraction). */
    public static String pyStr(Object v) {
        if (v instanceof Double d) {
            if (d == Math.rint(d) && !Double.isInfinite(d) && Math.abs(d) < 1e16) {
                return String.valueOf(d.longValue()) + ".0";
            }
            return d.toString();
        }
        if (v instanceof Float fl) {
            return pyStr(fl.doubleValue());
        }
        if (v instanceof BigDecimal bd) {
            return bd.toPlainString();
        }
        if (v instanceof Boolean b) {
            return b ? "True" : "False";
        }
        return String.valueOf(v);
    }
}
