package com.financetracker.shared.datastore;

import java.math.BigDecimal;
import java.time.Instant;
import java.time.LocalDate;
import java.time.LocalDateTime;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.Date;
import java.util.Map;
import java.util.concurrent.ExecutionException;

import com.financetracker.shared.web.Py;
import com.google.api.core.ApiFuture;
import com.google.cloud.Timestamp;

/**
 * Read/write helpers that keep Firestore documents in the format the Django code wrote:
 * decimals as strings, dates as ISO strings, datetimes as Firestore timestamps.
 */
public final class FirestoreDocs {

    private FirestoreDocs() {
    }

    public static <T> T await(ApiFuture<T> future) {
        try {
            return future.get();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted while waiting for Firestore", e);
        } catch (ExecutionException e) {
            throw new IllegalStateException("Firestore call failed: " + e.getCause().getMessage(), e.getCause());
        }
    }

    /** data.get(key, "") or "" */
    public static String str(Map<String, Object> d, String key) {
        Object v = d == null ? null : d.get(key);
        return v == null ? "" : String.valueOf(v);
    }

    /** data.get(key) with None preserved. */
    public static String strOrNull(Map<String, Object> d, String key) {
        Object v = d == null ? null : d.get(key);
        if (v == null) {
            return null;
        }
        String s = String.valueOf(v);
        return s.isEmpty() ? null : s;
    }

    /** bool(data.get(key, default)) with Python truthiness. */
    public static boolean bool(Map<String, Object> d, String key, boolean dflt) {
        if (d == null || !d.containsKey(key)) {
            return dflt;
        }
        return Py.truthy(d.get(key));
    }

    /** int(data.get(key, 0) or 0) */
    public static int integer(Map<String, Object> d, String key) {
        Object v = d == null ? null : d.get(key);
        if (v == null) {
            return 0;
        }
        if (v instanceof Number n) {
            return n.intValue();
        }
        try {
            return new BigDecimal(String.valueOf(v).strip()).intValue();
        } catch (NumberFormatException e) {
            return 0;
        }
    }

    /** _as_decimal(value): Decimal(str(value)), Decimal("0.00") when unparseable. */
    public static BigDecimal decimal(Map<String, Object> d, String key) {
        Object v = d == null ? null : d.get(key);
        return asDecimal(v);
    }

    public static BigDecimal asDecimal(Object v) {
        if (v == null) {
            return new BigDecimal("0.00");
        }
        try {
            if (v instanceof Double dbl) {
                return new BigDecimal(Double.toString(dbl));
            }
            return new BigDecimal(String.valueOf(v).strip());
        } catch (NumberFormatException e) {
            return new BigDecimal("0.00");
        }
    }

    public static BigDecimal decimalOrNull(Map<String, Object> d, String key) {
        Object v = d == null ? null : d.get(key);
        return v == null || "".equals(v) ? null : asDecimal(v);
    }

    /** _as_date(value): date, or the first 10 characters parsed as an ISO date. */
    public static LocalDate date(Map<String, Object> d, String key) {
        Object v = d == null ? null : d.get(key);
        if (v == null) {
            return null;
        }
        if (v instanceof Timestamp ts) {
            return ts.toDate().toInstant().atOffset(ZoneOffset.UTC).toLocalDate();
        }
        String s = String.valueOf(v);
        try {
            return LocalDate.parse(s.length() >= 10 ? s.substring(0, 10) : s);
        } catch (RuntimeException e) {
            return null;
        }
    }

    /** _as_datetime(value) as an instant (naive values are treated as UTC). */
    public static Instant instant(Map<String, Object> d, String key) {
        Object v = d == null ? null : d.get(key);
        if (v == null) {
            return null;
        }
        if (v instanceof Timestamp ts) {
            return Instant.ofEpochSecond(ts.getSeconds(), ts.getNanos());
        }
        if (v instanceof Date date) {
            return date.toInstant();
        }
        String s = String.valueOf(v);
        try {
            if (s.contains("T")) {
                String iso = s.replace("Z", "+00:00");
                try {
                    return OffsetDateTime.parse(iso).toInstant();
                } catch (RuntimeException e) {
                    return LocalDateTime.parse(iso).toInstant(ZoneOffset.UTC);
                }
            }
            return LocalDate.parse(s.substring(0, 10)).atStartOfDay().toInstant(ZoneOffset.UTC);
        } catch (RuntimeException e) {
            return null;
        }
    }

    public static Timestamp ts(Instant instant) {
        return instant == null ? null : Timestamp.ofTimeSecondsAndNanos(instant.getEpochSecond(), instant.getNano());
    }

    public static String isoDate(LocalDate date) {
        return date == null ? null : date.toString();
    }

    public static String decStr(BigDecimal value) {
        return value == null ? null : value.toPlainString();
    }
}
